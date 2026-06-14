import asyncio
import json
import queue
import logging

import websockets

from config import WS_PORT, WS_FALLBACK_PORT

log = logging.getLogger(__name__)


async def _handler(websocket, game_queue: queue.Queue):
    """Handle incoming WebSocket messages from the Chrome extension."""
    remote = websocket.remote_address
    log.info("Chrome extension connected: %s", remote)

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                game_name = data.get("game_name")

                if game_name is None:
                    # Clear presence
                    log.info("Extension sent clear signal")
                    game_queue.put({"source": "browser", "game_name": None})
                else:
                    log.info("Extension sent game: %s", game_name)
                    game_queue.put(data)

                # Send acknowledgment
                await websocket.send(json.dumps({
                    "status": "ok",
                    "received": game_name,
                }))

            except json.JSONDecodeError as exc:
                log.warning("Invalid JSON from extension: %s", exc)
                await websocket.send(json.dumps({
                    "status": "error",
                    "message": "invalid JSON",
                }))
            except Exception as exc:
                log.error("Error processing extension message: %s", exc)

    except websockets.exceptions.ConnectionClosed:
        log.info("Chrome extension disconnected: %s", remote)
    except Exception as exc:
        log.error("WebSocket handler error: %s", exc)


async def _serve(game_queue: queue.Queue, port: int):
    """Start the WebSocket server on the given port."""
    async with websockets.serve(
        lambda ws: _handler(ws, game_queue),
        "localhost",
        port,
    ):
        log.info("WebSocket server listening on localhost:%d", port)
        await asyncio.Future()  # run forever


async def start_server(game_queue: queue.Queue):
    """Start WebSocket server, try primary port then fallback."""
    try:
        await _serve(game_queue, WS_PORT)
    except OSError as exc:
        log.warning(
            "Port %d in use (%s), trying fallback port %d",
            WS_PORT, exc, WS_FALLBACK_PORT,
        )
        try:
            await _serve(game_queue, WS_FALLBACK_PORT)
        except OSError as exc2:
            log.error("Fallback port %d also in use: %s", WS_FALLBACK_PORT, exc2)
            log.error("WebSocket server could not start — Chrome extension will not work")
    except Exception as exc:
        log.error("WebSocket server error: %s", exc)
