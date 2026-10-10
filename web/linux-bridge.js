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
    const response = await browserFetch(...args);
    if (response.headers.get('content-type')?.includes('application/json')) {
      const body = await response.text();
      JSON.parse(body); // Reject incomplete replies rather than render empty license data.
      return new Response(body, {status: response.status, statusText: response.statusText, headers: response.headers});
    }
    return response; // File blobs and streaming job events retain their usual behavior.
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('linux-setup').href = '/setup' + location.hash;
    const previews = document.getElementById('linux-preview');
    if (previews) previews.href = '/preview' + location.hash;
  });
})();
