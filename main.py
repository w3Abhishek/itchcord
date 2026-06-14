import sys
import os
import asyncio
import queue
import logging
import time
import threading

from config import CLIENT_ID
from presence import PresenceManager, GameInfo
from watcher import Watcher
from server import start_server
from startup import is_startup_enabled, set_startup
from about import show_about_dialog

log = logging.getLogger("itchcord")

# Source priority: lower index = higher priority
SOURCE_PRIORITY = ["desktop_log", "desktop_process", "browser"]


def get_asset_path(filename: str) -> str:
    """Resolve asset path for both frozen (PyInstaller) and dev mode."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", filename)


def get_log_dir() -> str:
    """Get the directory for the log file."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logging() -> None:
    """Configure logging to both stdout and itchcord.log."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    # File handler
    log_path = os.path.join(get_log_dir(), "itchcord.log")
    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as e:
        root.warning("Could not create log file at %s: %s", log_path, e)


def _source_priority(source: str) -> int:
    """Return priority index for a source (lower = higher priority)."""
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY)


def create_tray(shutdown_event: threading.Event, current_game_name: list) -> threading.Thread | None:
    """Create and start the system tray icon in a daemon thread. Returns the thread or None on failure."""
    try:
        import pystray
        from PIL import Image
    except ImportError as e:
        log.warning("pystray or Pillow not installed, system tray disabled: %s", e)
        return None

    icon_path = get_asset_path("tray_icon.png")

    try:
        image = Image.open(icon_path)
    except Exception as e:
        log.warning("Could not load tray icon from %s: %s — using fallback", icon_path, e)
        try:
            # Fallback: create a simple 64x64 icon
            image = Image.new("RGBA", (64, 64), (108, 92, 231, 255))
        except Exception:
            log.error("Could not create fallback tray icon")
            return None

    def on_quit(icon, item):
        log.info("Quit requested from tray")
        shutdown_event.set()
        icon.stop()

    def get_status_text(item):
        name = current_game_name[0]
        return name if name else "No game detected"

    startup_enabled = [is_startup_enabled()]

    def toggle_startup(icon, item):
        new_state = not startup_enabled[0]
        set_startup(new_state)
        startup_enabled[0] = is_startup_enabled()

    def on_about(icon, item):
        logo_path = get_asset_path("itch_logo.png")
        threading.Thread(target=show_about_dialog, args=(logo_path,), daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("itchcord — Running", None, enabled=False),
        pystray.MenuItem(get_status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Run on Startup", toggle_startup, checked=lambda item: startup_enabled[0]),
        pystray.MenuItem("About", on_about),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon("itchcord", image, "itchcord", menu)

    def _run_tray():
        try:
            icon.run()
        except Exception as e:
            log.error("System tray error: %s", e)

    thread = threading.Thread(target=_run_tray, name="SysTray", daemon=True)
    thread.start()
    log.info("System tray started")
    return thread


def shutdown(watcher: Watcher, presence: PresenceManager) -> None:
    """Clean shutdown of all components."""
    log.info("Shutting down itchcord...")
    try:
        watcher.stop()
    except Exception as e:
        log.error("Error stopping watcher: %s", e)
    try:
        presence.clear()
    except Exception as e:
        log.error("Error clearing presence: %s", e)
    try:
        presence._disconnect()
    except Exception as e:
        log.error("Error disconnecting presence: %s", e)
    log.info("itchcord stopped")


def main() -> None:
    setup_logging()
    log.info("itchcord starting...")
    
    # Enforce Run on Startup by default
    if not is_startup_enabled():
        log.info("Enabling 'Run on Startup' by default.")
        set_startup(True)

    game_queue: queue.Queue[GameInfo | None] = queue.Queue()
    shutdown_event = threading.Event()
    # Mutable container so tray menu callback can read current game name
    current_game_name: list[str | None] = [None]

    # Start subsystems
    watcher = Watcher(game_queue)
    watcher.start()

    # Start WebSocket server in a daemon thread
    ws_thread = threading.Thread(
        target=lambda: asyncio.run(start_server(game_queue)),
        daemon=True,
        name="ws-server",
    )
    ws_thread.start()

    presence = PresenceManager(CLIENT_ID)
    presence.connect()

    create_tray(shutdown_event, current_game_name)

    # Track current active presence
    active_source: str | None = None
    active_game: GameInfo | None = None

    log.info("itchcord is running. Waiting for game events...")

    try:
        while not shutdown_event.is_set():
            try:
                item = game_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:
                # Clear presence — but only if the clear comes from the active source
                # Since we don't track source on None, clear unconditionally
                # unless a higher-priority source is active
                if active_game is not None:
                    log.info("Clearing presence (was: %s)", active_game.game_name)
                    presence.clear()
                    active_game = None
                    active_source = None
                    current_game_name[0] = None
                continue

            # item is a dict from the queue — convert to GameInfo
            if isinstance(item, dict):
                game_name = item.get("game_name")
                source = item.get("source", "browser")

                if game_name is None or not item.get("is_playing", False):
                    # Game stopped — only clear if source matches active source
                    if active_source is None or active_source == source:
                        log.info("Game stopped (source=%s)", source)
                        presence.clear()
                        active_game = None
                        active_source = None
                        current_game_name[0] = None
                    continue

                # Build GameInfo from dict
                try:
                    game = GameInfo(
                        source=source,
                        game_name=game_name,
                        game_url=item.get("game_url"),
                        cover_image=item.get("cover_image"),
                        is_playing=True,
                        started_at=item.get("started_at", int(time.time())),
                        game_id=item.get("game_id"),
                        developer=item.get("developer"),
                    )
                except Exception as exc:
                    log.error("Failed to create GameInfo: %s", exc)
                    continue
            elif isinstance(item, GameInfo):
                game = item
                source = game.source
            else:
                log.warning("Unknown item type in queue: %s", type(item))
                continue

            # Check source priority: only update if new source has equal or higher priority
            if active_source is not None:
                current_priority = _source_priority(active_source)
                new_priority = _source_priority(source)
                if new_priority > current_priority:
                    log.debug(
                        "Ignoring lower-priority source %s (current: %s)",
                        source,
                        active_source,
                    )
                    continue

            # Update presence
            presence.update(game)
            active_game = game
            active_source = game.source
            current_game_name[0] = game.game_name

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received")
    except Exception as e:
        log.error("Unexpected error in main loop: %s", e)
    finally:
        shutdown(watcher, presence)


if __name__ == "__main__":
    main()
