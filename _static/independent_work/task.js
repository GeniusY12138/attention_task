/* oTree supplies liveSend; the database owns elapsed time and scored responses. */
(() => {
  'use strict';
  if (window.__independentWorkStarted) return;
  window.__independentWorkStarted = true;
  const clientId = window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  const status = document.getElementById('statusLine');
  const timer = document.getElementById('timerLine');
  const box = document.getElementById('promptBox');
  const input = document.getElementById('promptInput');
  const text = document.getElementById('promptText');
  const hint = document.getElementById('promptHint');
  const promptTime = document.getElementById('promptTime');
  const waiting = document.getElementById('waitingText');
  let initialized = false, stopped = false, submitting = false;
  let state = null, lastReply = 0, displayedId = null, shownAt = 0, responsePending = false;

  function send(type, extra = {}) {
    if (stopped || submitting) return;
    try {
      liveSend({type, client_id: clientId, visible: document.visibilityState === 'visible', ...extra});
    } catch (_) {
      status.textContent = 'Connection interrupted. Reconnecting…';
    }
  }

  window.liveRecv = function (data) {
    if (data.recipient !== clientId) return;
    if (data.type === 'inactive_tab') {
      stopped = true;
      input.disabled = true;
      status.textContent = 'This participant link is open in another tab. Use that tab, or reload this one to resume here.';
      return;
    }
    if (data.type === 'error') {
      stopped = true;
      status.textContent = data.message;
      return;
    }
    if (data.type !== 'state') return;
    initialized = true;
    state = data;
    lastReply = performance.now();
    if (data.complete) {
      submitting = true;
      timer.textContent = '00:00';
      box.hidden = true;
      waiting.hidden = true;
      status.textContent = 'Work complete. Saving results…';
      document.getElementById('form').submit();
      return;
    }
    if (data.prompt && data.prompt.id !== displayedId) {
      displayedId = data.prompt.id;
      shownAt = performance.now();
      responsePending = false;
      box.hidden = false;
      waiting.hidden = true;
      text.textContent = data.prompt.text;
      hint.textContent = data.prompt.hint;
      input.hidden = data.prompt.type !== 'text';
      input.disabled = false;
      input.value = '';
      if (!input.hidden && document.visibilityState === 'visible') input.focus();
    } else if (!data.prompt) {
      displayedId = null;
      responsePending = false;
      box.hidden = true;
      waiting.hidden = false;
    }
    render();
  };

  function render() {
    if (!state || stopped || submitting) return;
    const sinceReply = performance.now() - lastReply;
    const connected = sinceReply < 2500;
    const visible = document.visibilityState === 'visible';
    status.textContent = !connected ? 'Connection interrupted. Work time is paused; reconnecting…'
      : !visible ? 'Work time paused while this tab is hidden.' : 'Task running…';
    // Display the last acknowledged amount; never suggest completion before the server confirms it.
    const seconds = Math.ceil(state.remaining_ms / 1000);
    timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    if (state.prompt) {
      const remaining = Math.max(0, state.prompt.deadline - state.server_now - sinceReply);
      promptTime.textContent = responsePending ? 'Answer sent…' : `Respond within ${Math.ceil(remaining / 1000)} seconds`;
      input.disabled = responsePending || !connected || remaining <= 0;
    }
  }

  document.getElementById('form').addEventListener('submit', event => {
    if (!submitting) event.preventDefault();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Enter') event.preventDefault();
    if (!state || !state.prompt || stopped || submitting || responsePending || document.visibilityState !== 'visible') return;
    if (performance.now() - lastReply >= 2500) return;
    const prompt = state.prompt;
    let response;
    if (prompt.type === 'key' && ['F', 'J'].includes(event.key.toUpperCase())) response = event.key.toUpperCase();
    else if (prompt.type === 'key_lr' && ['ArrowLeft', 'ArrowRight'].includes(event.key)) response = event.key;
    else if (prompt.type === 'text' && event.key === 'Enter') response = input.value.trim();
    if (response === undefined) return;
    event.preventDefault();
    responsePending = true;
    send('response', {prompt_id: prompt.id, response, client_rt_ms: performance.now() - shownAt});
    render();
  });
  document.addEventListener('visibilitychange', () => { send('visibility'); render(); });
  window.addEventListener('blur', () => send('blur'));
  window.addEventListener('pagehide', () => send('leave'));
  window.addEventListener('online', () => send(initialized ? 'heartbeat' : 'hello'));
  document.addEventListener('DOMContentLoaded', () => {
    send('hello');
    setInterval(() => send(initialized ? 'heartbeat' : 'hello'), 1000);
    setInterval(render, 100);
  });
})();
