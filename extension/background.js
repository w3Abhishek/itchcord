// background.js — itchcord service worker
// Persistent WebSocket to local bridge + message relay from content scripts

(function () {
  'use strict';

  const WS_URL = 'ws://localhost:6969';
  const BACKOFF_INITIAL_MS = 3000;
  const BACKOFF_MAX_MS = 30000;

  // ── State ───────────────────────────────────────────────────────────────

  let ws = null;
  let backoffMs = BACKOFF_INITIAL_MS;
  let reconnectTimer = null;
  let activeTabId = null;
  let activeGame = null; // { gameName, gameUrl, coverImage, startedAt }
  let messageBuffer = []; // buffered payloads while WS is disconnected

  // ── WebSocket management ────────────────────────────────────────────────

  function isConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
  }

  function sendPayload(payload) {
    const json = JSON.stringify(payload);
    if (isConnected()) {
      ws.send(json);
      console.log('[itchcord:bg] Sent:', payload);
    } else {
      messageBuffer.push(json);
      console.log('[itchcord:bg] Buffered (WS not connected):', payload);
    }
  }

  function flushBuffer() {
    if (!isConnected() || messageBuffer.length === 0) return;
    console.log(`[itchcord:bg] Flushing ${messageBuffer.length} buffered message(s)`);
    for (const json of messageBuffer) {
      ws.send(json);
    }
    messageBuffer = [];
  }

  function connect() {
    if (ws) {
      try {
        ws.close();
      } catch (_) {
        // ignore
      }
    }

    console.log(`[itchcord:bg] Connecting to ${WS_URL}...`);
    ws = new WebSocket(WS_URL);

    ws.addEventListener('open', () => {
      console.log('[itchcord:bg] WebSocket connected');
      backoffMs = BACKOFF_INITIAL_MS; // reset backoff on success
      flushBuffer();
    });

    ws.addEventListener('close', (event) => {
      console.log(
        `[itchcord:bg] WebSocket closed (code=${event.code}). Reconnecting in ${backoffMs}ms...`
      );
      scheduleReconnect();
    });

    ws.addEventListener('error', (error) => {
      console.error('[itchcord:bg] WebSocket error:', error);
      // 'close' will fire after 'error', so reconnect is handled there
    });

    ws.addEventListener('message', (event) => {
      console.log('[itchcord:bg] Received from server:', event.data);
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, backoffMs);
    // Exponential backoff capped at max
    backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
  }

  // ── Game state management ──────────────────────────────────────────────

  function setPlaying(tabId, gameName, gameUrl, coverImage) {
    const startedAt = Math.floor(Date.now() / 1000);
    activeTabId = tabId;
    activeGame = { gameName, gameUrl, coverImage, startedAt };

    sendPayload({
      source: 'browser',
      game_name: gameName,
      game_url: gameUrl,
      cover_image: coverImage,
      is_playing: true,
      started_at: startedAt,
    });
  }

  function clearPlaying() {
    if (!activeGame) return; // nothing to clear
    activeTabId = null;
    activeGame = null;

    sendPayload({
      source: 'browser',
      game_name: null,
      is_playing: false,
    });
  }

  // ── Message listener (from content scripts) ────────────────────────────

  chrome.runtime.onMessage.addListener((message, sender, _sendResponse) => {
    const tabId = sender.tab?.id;
    console.log('[itchcord:bg] Message from content script:', message, 'tab:', tabId);

    switch (message.type) {
      case 'GAME_STARTED':
        // Last GAME_STARTED wins — only one game active at a time
        setPlaying(tabId, message.gameName, message.gameUrl, message.coverImage);
        break;

      case 'GAME_STOPPED':
        // Only clear if this tab is the active game tab
        if (tabId === activeTabId) {
          clearPlaying();
        }
        break;

      case 'TAB_CLOSED':
        if (tabId === activeTabId) {
          clearPlaying();
        }
        break;

      default:
        console.warn('[itchcord:bg] Unknown message type:', message.type);
    }
  });

  // ── Tab lifecycle listeners ────────────────────────────────────────────

  // Tab removed entirely
  chrome.tabs.onRemoved.addListener((tabId, _removeInfo) => {
    if (tabId === activeTabId) {
      console.log('[itchcord:bg] Active game tab removed:', tabId);
      clearPlaying();
    }
  });

  // Tab navigated away from itch.io
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, _tab) => {
    if (tabId !== activeTabId) return;
    if (!changeInfo.url) return;

    try {
      const url = new URL(changeInfo.url);
      const isItch = url.hostname.endsWith('.itch.io') && url.hostname !== 'itch.io';
      if (!isItch) {
        console.log('[itchcord:bg] Active game tab navigated away from itch.io:', changeInfo.url);
        clearPlaying();
      }
    } catch (_) {
      // If URL parsing fails, clear to be safe
      clearPlaying();
    }
  });

  // ── Boot ───────────────────────────────────────────────────────────────

  connect();
  console.log('[itchcord:bg] Service worker started');
})();
