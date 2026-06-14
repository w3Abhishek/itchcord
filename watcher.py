import os
import re
import time
import queue
import logging
import threading

import psutil

from config import get_itch_log_path, get_itch_apps_dir, LOG_POLL_INTERVAL, POLL_INTERVAL
from db import get_game_metadata, get_game_metadata_by_folder

log = logging.getLogger(__name__)

# ── Log parsing patterns ────────────────────────────────────────────────

# Game launched — both native and HTML games log this
LAUNCH_RE = re.compile(r"launching '(.+?)' \(#(\d+)\)")

# Game exited
EXIT_PATTERNS = ['"Wait done"', '"Exited!"', 'Session ended normally']


class Watcher:
    """Watches for itch.io games via log tailing and process scanning."""

    def __init__(self, game_queue: queue.Queue):
        self._queue = game_queue
        self._running = False
        self._threads: list[threading.Thread] = []

    def start(self):
        """Start log tailer and process scanner threads."""
        self._running = True

        log_path = get_itch_log_path()
        if log_path and os.path.exists(log_path):
            t = threading.Thread(target=self._log_tailer, daemon=True, name="log-tailer")
            self._threads.append(t)
            t.start()
            log.info("Log tailer started: %s", log_path)
        else:
            log.info("itch log file not found, log tailer skipped")

        t = threading.Thread(target=self._process_scanner, daemon=True, name="process-scanner")
        self._threads.append(t)
        t.start()
        log.info("Process scanner started")

    def stop(self):
        """Signal threads to stop."""
        self._running = False
        log.info("Watcher stopping")

    # ── Log Tailer ──────────────────────────────────────────────────────

    def _log_tailer(self):
        """Tail the itch desktop app log file in realtime."""
        log_path = get_itch_log_path()
        if not log_path:
            return

        f = None
        file_inode = None

        while self._running:
            try:
                # Open or reopen the file
                if f is None:
                    if not os.path.exists(log_path):
                        time.sleep(LOG_POLL_INTERVAL * 10)
                        continue
                    f = open(log_path, "r", encoding="utf-8", errors="replace")
                    f.seek(0, 2)  # seek to end
                    try:
                        file_inode = os.stat(log_path).st_ino
                    except OSError:
                        file_inode = None
                    log.debug("Log file opened, seeking to end")

                # Check for log rotation
                try:
                    current_pos = f.tell()
                    stat = os.stat(log_path)
                    if stat.st_size < current_pos:
                        log.info("Log file rotated (shrunk), reopening")
                        f.close()
                        f = None
                        continue
                    if file_inode is not None and stat.st_ino != file_inode:
                        log.info("Log file rotated (new inode), reopening")
                        f.close()
                        f = None
                        continue
                except OSError:
                    log.info("Log file disappeared, reopening")
                    f.close()
                    f = None
                    continue

                # Read new lines
                line = f.readline()
                if not line:
                    time.sleep(LOG_POLL_INTERVAL)
                    continue

                line = line.strip()
                if not line:
                    continue

                # Check for launch
                match = LAUNCH_RE.search(line)
                if match:
                    game_name = match.group(1)
                    game_id = int(match.group(2))
                    log.info("Game launched: %s (#%d)", game_name, game_id)

                    # Query butler.db for metadata
                    metadata = get_game_metadata(game_id)
                    game_url = None
                    cover_image = None
                    developer = None

                    if metadata:
                        game_name = metadata.get("title", game_name)
                        game_url = metadata.get("url")
                        cover_image = metadata.get("cover_url")
                        developer = metadata.get("developer")

                    self._queue.put({
                        "source": "desktop_log",
                        "game_name": game_name,
                        "game_url": game_url,
                        "cover_image": cover_image,
                        "is_playing": True,
                        "started_at": int(time.time()),
                        "game_id": game_id,
                        "developer": developer,
                    })
                    continue

                # Check for exit
                if any(pattern in line for pattern in EXIT_PATTERNS):
                    log.info("Game exited (log pattern matched)")
                    self._queue.put({"source": "desktop_log", "game_name": None})
                    continue

            except Exception as exc:
                log.error("Log tailer error: %s", exc)
                if f:
                    try:
                        f.close()
                    except Exception:
                        pass
                    f = None
                time.sleep(LOG_POLL_INTERVAL * 5)

        if f:
            try:
                f.close()
            except Exception:
                pass

    # ── Process Scanner ─────────────────────────────────────────────────

    def _process_scanner(self):
        """Scan running processes for itch.io games as a fallback."""
        apps_dir = get_itch_apps_dir()
        if not apps_dir:
            log.info("itch apps directory not configured, process scanner idle")
            # Still run the loop in case it becomes available
            while self._running:
                time.sleep(POLL_INTERVAL)
            return

        previous_game = None

        while self._running:
            try:
                current_game = self._find_itch_process(apps_dir)

                if current_game and current_game != previous_game:
                    log.info("Process scanner found game folder: %s", current_game)

                    # Enrich with metadata from butler.db via folder name
                    game_name = current_game
                    game_url = None
                    cover_image = None
                    game_id = None
                    developer = None

                    metadata = get_game_metadata_by_folder(current_game)
                    if metadata:
                        game_name = metadata.get("title", current_game)
                        game_url = metadata.get("url")
                        cover_image = metadata.get("cover_url")
                        game_id = metadata.get("game_id")
                        developer = metadata.get("developer")
                        log.info("Resolved folder '%s' → '%s' (cover: %s)",
                                 current_game, game_name,
                                 cover_image[:50] if cover_image else "None")

                    self._queue.put({
                        "source": "desktop_process",
                        "game_name": game_name,
                        "game_url": game_url,
                        "cover_image": cover_image,
                        "is_playing": True,
                        "started_at": int(time.time()),
                        "game_id": game_id,
                        "developer": developer,
                    })
                    previous_game = current_game
                elif not current_game and previous_game:
                    log.info("Process scanner: game %s no longer running", previous_game)
                    self._queue.put({"source": "desktop_process", "game_name": None})
                    previous_game = None

            except Exception as exc:
                log.error("Process scanner error: %s", exc)

            time.sleep(POLL_INTERVAL)

    @staticmethod
    def _find_itch_process(apps_dir: str) -> str | None:
        """Find a running process whose exe is inside the itch apps directory."""
        apps_dir_lower = apps_dir.lower()

        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                exe = proc.info["exe"]
                if exe and apps_dir_lower in exe.lower():
                    # exe looks like: .../itch/apps/celeste/Celeste.exe
                    # game folder name is one level above exe
                    game_folder = os.path.basename(os.path.dirname(exe))
                    if game_folder:
                        return game_folder
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

        return None
