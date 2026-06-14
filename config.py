import sys
import os

# Discord Rich Presence Application ID
CLIENT_ID = "1515806299445526689"

# WebSocket server port for Chrome extension
WS_PORT = 6969
WS_FALLBACK_PORT = 6970

# Polling intervals (seconds)
POLL_INTERVAL = 5        # process scanner
LOG_POLL_INTERVAL = 0.5  # log file tailer

# Retry intervals
DISCORD_RETRY_INTERVAL = 30  # seconds between Discord reconnect attempts


def get_butler_db_path():
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            return None
        return os.path.join(appdata, "itch", "db", "butler.db")
    elif sys.platform == "linux":
        return os.path.expanduser("~/.config/itch/db/butler.db")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/itch/db/butler.db")
    return None


def get_itch_log_path():
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            return None
        return os.path.join(appdata, "itch", "logs", "itch.txt")
    elif sys.platform == "linux":
        return os.path.expanduser("~/.config/itch/logs/itch.txt")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/itch/logs/itch.txt")
    return None


def get_itch_apps_dir():
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        if not appdata:
            return None
        return os.path.join(appdata, "itch", "apps")
    elif sys.platform == "linux":
        return os.path.expanduser("~/.config/itch/apps")
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/itch/apps")
    return None
