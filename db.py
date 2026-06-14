import sqlite3
import os
import logging
from config import get_butler_db_path

log = logging.getLogger(__name__)


def _connect_readonly():
    """Open a read-only connection to butler.db, or return None."""
    db_path = get_butler_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        log.warning("Could not open butler.db: %s", e)
        return None


def get_game_metadata(game_id: int) -> dict | None:
    """Query butler.db for game metadata by game_id.

    Returns dict with title, url, cover_url, short_text, developer or None.
    """
    con = _connect_readonly()
    if not con:
        return None
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT g.title, g.url, g.cover_url, g.short_text, u.display_name
            FROM games g
            LEFT JOIN users u ON g.user_id = u.id
            WHERE g.id = ?
        """, (game_id,))
        row = cur.fetchone()
        if row:
            return {
                "title": row[0],
                "url": row[1],
                "cover_url": row[2],
                "short_text": row[3],
                "developer": row[4],
            }
        return None
    except sqlite3.OperationalError as e:
        log.warning("Could not read butler.db: %s", e)
        return None
    except Exception as e:
        log.error("Unexpected error reading butler.db: %s", e)
        return None
    finally:
        con.close()


def get_game_metadata_by_folder(folder_name: str) -> dict | None:
    """Look up game metadata by install folder name (used by the process scanner).

    Joins caves → games → users to resolve the folder name into full game info.
    """
    con = _connect_readonly()
    if not con:
        return None
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT g.id, g.title, g.url, g.cover_url, g.short_text, u.display_name
            FROM caves c
            JOIN games g ON c.game_id = g.id
            LEFT JOIN users u ON g.user_id = u.id
            WHERE c.install_folder_name = ?
            LIMIT 1
        """, (folder_name,))
        row = cur.fetchone()
        if row:
            return {
                "game_id": row[0],
                "title": row[1],
                "url": row[2],
                "cover_url": row[3],
                "short_text": row[4],
                "developer": row[5],
            }
        return None
    except sqlite3.OperationalError as e:
        log.warning("Could not read butler.db: %s", e)
        return None
    except Exception as e:
        log.error("Unexpected error reading butler.db: %s", e)
        return None
    finally:
        con.close()
