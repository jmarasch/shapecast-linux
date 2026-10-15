/* Connection supplied by the Linux launcher; original UI assets stay unchanged. */
(() => {
  'use strict';
  const params = new URLSearchParams(location.hash.slice(1));
  const port = Number(params.get('core'));
  const token = params.get('token');
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !/^[A-Za-z0-9_-]{32,128}$/.test(token || '')) {
    document.addEventListener('DOMContentLoaded', () => {
      document.getElementById('root').textContent = 'Open Shapecast using the Linux launcher to connect to its local engine.';
    });
    return;
  }
  window.__SHAPECAST__ = Object.freeze({baseUrl: `http://127.0.0.1:${port}`, token});
  // Buffer and validate JSON before handing it to the embedded UI.
  // Incomplete replies must not become empty license objects.
  const browserFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const request = args[0];
    const url = new URL(request instanceof Request ? request.url : request, location.href);
    const method = (args[1]?.method || (request instanceof Request ? request.method : 'GET')).toUpperCase();
    // The original UI requests hardware only once. Retry interrupted local reads;
    // never repeat writes, external requests, or deliberate HTTP error replies.
    const attempts = url.origin === window.__SHAPECAST__.baseUrl && method === 'GET' ? 3 : 1;
    for (let attempt = 0; attempt < attempts; attempt++) {
      try {
        const response = await browserFetch(...args);
        if (response.headers.get('content-type')?.includes('application/json')) {
          const body = await response.text();
          JSON.parse(body); // Reject incomplete replies rather than render empty license data.
          return new Response(body, {status: response.status, statusText: response.statusText, headers: response.headers});
        }
        return response; // File blobs and streaming job events retain their usual behavior.
      } catch (error) {
        if (attempt + 1 === attempts || args[1]?.signal?.aborted || (request instanceof Request && request.signal.aborted)) throw error;
        console.warn(`Retrying interrupted local read: ${url.pathname}`, error.message);
        await new Promise(resolve => setTimeout(resolve, 250 * (attempt + 1)));
      }
    }
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('linux-setup').href = '/setup' + location.hash;
    const previews = document.getElementById('linux-preview');
    if (previews) previews.href = '/preview' + location.hash;
  });
})();
