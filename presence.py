import time
import logging
from dataclasses import dataclass

from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, DiscordError, InvalidID

log = logging.getLogger(__name__)


@dataclass
class GameInfo:
    source: str            # "desktop_log" | "desktop_process" | "browser"
    game_name: str
    game_url: str | None
    cover_image: str | None
    is_playing: bool
    started_at: int        # unix timestamp
    game_id: int | None = None   # itch game id if known
    developer: str | None = None # game developer display name


class PresenceManager:
    """Wraps pypresence with connect/reconnect/clear logic and retry backoff.

    Discord Rich Presence limitations:
    - The activity title is ALWAYS the registered Discord application name
      ("itchcord"). This CANNOT be changed dynamically via RPC — it is
      hard-coded per application ID in the Discord Developer Portal.
    - However, large_image/small_image DO support external HTTPS URLs.
      Discord proxies them automatically, so we can show itch.io cover art
      directly without uploading assets to the Developer Portal.
    - details + state are fully customizable strings.
    """

    MAX_RETRIES = 5
    INITIAL_BACKOFF = 2  # seconds

    def __init__(self, client_id: str):
        self._client_id = client_id
        self._rpc = Presence(client_id)
        self._connected = False

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Try to connect to Discord, retry with exponential backoff.
        Returns True if connected, False otherwise."""
        if self._connected:
            return True

        backoff = self.INITIAL_BACKOFF
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._rpc = Presence(self._client_id)
                self._rpc.connect()
                self._connected = True
                log.info("Connected to Discord RPC")
                return True
            except DiscordNotFound:
                log.warning(
                    "Discord not found (attempt %d/%d). Retrying in %ds...",
                    attempt, self.MAX_RETRIES, backoff,
                )
            except (DiscordError, InvalidID) as exc:
                log.warning(
                    "Discord error (attempt %d/%d): %s. Retrying in %ds...",
                    attempt, self.MAX_RETRIES, exc, backoff,
                )
            except (ConnectionRefusedError, BrokenPipeError, OSError) as exc:
                log.warning(
                    "Connection error (attempt %d/%d): %s. Retrying in %ds...",
                    attempt, self.MAX_RETRIES, exc, backoff,
                )
            except Exception as exc:
                log.error(
                    "Unexpected error connecting (attempt %d/%d): %s. Retrying in %ds...",
                    attempt, self.MAX_RETRIES, exc, backoff,
                )
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

        log.error("Failed to connect to Discord after %d attempts", self.MAX_RETRIES)
        self._connected = False
        return False

    def reconnect(self) -> bool:
        """Disconnect and reconnect with backoff."""
        self._disconnect()
        return self.connect()

    def _disconnect(self):
        """Safely disconnect from Discord."""
        try:
            if self._connected:
                self._rpc.close()
        except Exception as exc:
            log.debug("Error during disconnect: %s", exc)
        finally:
            self._connected = False

    def _ensure_connected(self) -> bool:
        """Auto-reconnect if disconnected."""
        if self._connected:
            return True
        log.info("Not connected to Discord, attempting reconnect...")
        return self.connect()

    # ── Presence ────────────────────────────────────────────────────────

    def update(self, game: GameInfo):
        """Update Discord Rich Presence with game info.

        Target layout in Discord:
            itchcord                    ← app name (immutable, set in Developer Portal)
            Playing Metropolis 1998     ← details
            via itch.io                 ← state

            [Game Cover Art]            ← large_image (external URL from itch.io)
              [source icon]             ← small_image
            Elapsed: 00:13:37           ← start timestamp

            [View on itch.io]           ← button
        """
        if not self._ensure_connected():
            return

        # ── Large image: game cover art via external URL ────────────────
        # Discord RPC supports external HTTPS URLs in large_image/small_image.
        # itch.io cover URLs (https://img.itch.zone/...) work directly.
        large_image = game.cover_image if game.cover_image else "itch_logo"
        large_text = game.game_name

        # ── Small image: source indicator ───────────────────────────────
        is_desktop = game.source.startswith("desktop")
        small_image = "icon_desktop" if is_desktop else "icon_browser"
        small_text = "itch desktop app" if is_desktop else "browser"

        # ── Details / State ─────────────────────────────────────────────
        details = game.game_name
        if game.developer:
            state = f"by {game.developer} — via itch.io"
        else:
            state = "via itch.io"

        # ── Buttons ─────────────────────────────────────────────────────
        buttons = None
        if game.game_url:
            buttons = [{"label": "View on itch.io", "url": game.game_url}]

        try:
            self._rpc.update(
                details=details,
                state=state,
                large_image=large_image,
                large_text=large_text,
                small_image=small_image,
                small_text=small_text,
                start=game.started_at,
                buttons=buttons,
            )
            log.info("Presence updated: %s [large_image=%s]", game.game_name,
                     large_image[:60] if large_image else "None")
        except (DiscordNotFound, DiscordError, InvalidID) as exc:
            log.warning("Discord error updating presence: %s", exc)
            self._connected = False
        except (ConnectionRefusedError, BrokenPipeError, OSError) as exc:
            log.warning("Connection error updating presence: %s", exc)
            self._connected = False
        except Exception as exc:
            log.error("Unexpected error updating presence: %s", exc)
            self._connected = False

    def clear(self):
        """Clear Discord Rich Presence."""
        if not self._ensure_connected():
            return

        try:
            self._rpc.clear()
            log.info("Presence cleared")
        except (DiscordNotFound, DiscordError, InvalidID) as exc:
            log.warning("Discord error clearing presence: %s", exc)
            self._connected = False
        except (ConnectionRefusedError, BrokenPipeError, OSError) as exc:
            log.warning("Connection error clearing presence: %s", exc)
            self._connected = False
        except Exception as exc:
            log.error("Unexpected error clearing presence: %s", exc)
            self._connected = False
