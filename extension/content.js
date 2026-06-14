// content.js — itchcord content script
// Runs on *.itch.io/* pages, detects game play via iframe#game_drop

(function () {
  'use strict';

  // ── Gate: only run on game pages ──────────────────────────────────────
  // Valid pattern: <username>.itch.io/<gamename>  (one path segment only)
  // Reject: plain itch.io, or paths like /games, /jams, /dashboard, etc.

  const hostname = location.hostname;
  const pathname = location.pathname;

  // Must be a subdomain of itch.io (not plain "itch.io")
  if (hostname === 'itch.io' || hostname === 'www.itch.io') return;
  if (!hostname.endsWith('.itch.io')) return;

  // Pathname must be exactly /<something> — one segment, no deeper slashes
  // Allow optional trailing slash: /gamename or /gamename/
  const cleanPath = pathname.replace(/\/+$/, ''); // strip trailing slashes
  if (!cleanPath || cleanPath === '') return; // bare subdomain root, e.g. user.itch.io
  if (!/^\/[^/]+$/.test(cleanPath)) return; // must be single segment like /gamename

  // ── Scrape game info from og: meta tags ───────────────────────────────

  function getMeta(property) {
    const el =
      document.querySelector(`meta[property="${property}"]`) ||
      document.querySelector(`meta[name="${property}"]`);
    return el ? el.getAttribute('content') : null;
  }

  const gameName = getMeta('og:title') || document.title || 'Unknown Game';
  const coverImage = getMeta('og:image') || '';
  const gameUrl = getMeta('og:url') || location.href;

  console.log('[itchcord] Game page detected:', { gameName, gameUrl, coverImage });

  // ── Messaging helpers ─────────────────────────────────────────────────

  let currentlyPlaying = false;

  function sendGameStarted() {
    if (currentlyPlaying) return; // avoid duplicate messages
    currentlyPlaying = true;
    console.log('[itchcord] Game started:', gameName);
    chrome.runtime.sendMessage({
      type: 'GAME_STARTED',
      gameName,
      gameUrl,
      coverImage,
    });
  }

  function sendGameStopped() {
    if (!currentlyPlaying) return;
    currentlyPlaying = false;
    console.log('[itchcord] Game stopped');
    chrome.runtime.sendMessage({ type: 'GAME_STOPPED' });
  }

  function sendTabClosed() {
    console.log('[itchcord] Tab closing');
    chrome.runtime.sendMessage({ type: 'TAB_CLOSED' });
  }

  // ── Check if iframe#game_drop exists right now (refresh mid-game) ─────

  function isGameIframePresent() {
    return !!document.querySelector('iframe#game_drop');
  }

  if (isGameIframePresent()) {
    sendGameStarted();
  }

  // ── MutationObserver: watch for iframe#game_drop appear/disappear ─────

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      // Check added nodes
      for (const node of mutation.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (
          (node.tagName === 'IFRAME' && node.id === 'game_drop') ||
          node.querySelector?.('iframe#game_drop')
        ) {
          sendGameStarted();
        }
      }

      // Check removed nodes
      for (const node of mutation.removedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (
          (node.tagName === 'IFRAME' && node.id === 'game_drop') ||
          node.querySelector?.('iframe#game_drop')
        ) {
          sendGameStopped();
        }
      }
    }
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  });

  // ── Tab close / navigate away ─────────────────────────────────────────

  window.addEventListener('beforeunload', () => {
    sendTabClosed();
  });
})();
