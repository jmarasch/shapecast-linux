/* Review images before any geometry work is queued. No vendor UI files are edited. */
(() => {
  'use strict';
  const connection = () => window.__SHAPECAST__;
  let reviews = [], currentId = null, busy = false, signature = '', focused = null, actionError = '';
  const seen = new Set();
  const background = new Map();
  let refreshNumber = 0, appliedRefresh = 0;
  const labels = {front: 'Front reference', left: 'Left side', back: 'Back', right: 'Right side'};
  const banner = document.createElement('aside');
  banner.id = 'linux-view-review-banner'; banner.hidden = true;
  banner.setAttribute('aria-label', 'Alternate view approvals');
  const overlay = document.createElement('div');
  overlay.id = 'linux-view-review'; overlay.hidden = true;
  overlay.innerHTML = `<section role="dialog" aria-modal="true" aria-labelledby="lvr-title" tabindex="-1">
    <header><div><p class="lvr-eyebrow">BEFORE GEOMETRY</p><h2 id="lvr-title">Review alternate views</h2></div>
    <div class="lvr-header-actions"><button type="button" data-action="refresh">Refresh images</button><button type="button" data-action="later">Review later</button></div></header>
    <p id="lvr-job"></p><p>Compare each angle with the front reference. Approve the views you like, or regenerate an individual view. Your approved views stay unchanged.</p>
    <p id="lvr-status" role="status" aria-live="polite"></p><p id="lvr-error" role="alert" hidden></p>
    <div id="lvr-cards"></div><div id="lvr-zoom" hidden><button type="button" data-action="unzoom">Back to views</button><img alt=""></div>
    <footer><button type="button" data-action="cancel">Cancel cast</button><span>Geometry stays paused until you continue.</span>
    <button type="button" class="lvr-primary" data-action="continue">Continue to geometry</button></footer>
  </section>`;
  function element(tag, text, cls) {
    const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls; return node;
  }
  function request(path, body, type = 'json') {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(body === undefined ? 'GET' : 'POST', '/linux-view-review-api'+path);
      xhr.responseType = type; xhr.timeout = 25000;
      xhr.setRequestHeader('Authorization', 'Bearer '+connection().token);
      if (body !== undefined) xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
        else reject(new Error(type === 'json' && typeof xhr.response?.detail === 'string'
          ? xhr.response.detail : 'Could not update this review. Try again.'));
      };
      xhr.onerror = xhr.ontimeout = () => reject(new Error('Could not reach the local image review service. Try again.'));
      xhr.send(body === undefined ? null : JSON.stringify(body));
    });
  }
  async function api(path, body) {
    return request(path, body);
  }
  function loadImage(review, name, image, approveButton) {
    image.onload = () => {
      if (approveButton?.isConnected && !busy && review.phase === 'pending') approveButton.disabled = false;
    };
    image.onerror = () => {
      console.warn('Review image unavailable: '+name+'; image address present: '+Boolean(image.getAttribute('src')));
      if (image.isConnected) image.replaceWith(element('p', 'Image unavailable. Choose Refresh images to try again.', 'lvr-image-error'));
    };
    if (review.images?.[name]?.startsWith('/linux-view-review-image/')) image.src = review.images[name];
    else image.onerror();
  }
  function close() {
    overlay.hidden = true; currentId = null; signature = ''; actionError = '';
    for (const [node, hidden] of background) {
      if (hidden === null) node.removeAttribute('aria-hidden'); else node.setAttribute('aria-hidden', hidden);
    }
    background.clear();
    const zoom = overlay.querySelector('#lvr-zoom'); zoom.hidden = true;
    if (focused?.isConnected) focused.focus();
    renderBanner();
  }
  function show(id) {
    currentId = id; focused = document.activeElement; signature = ''; overlay.hidden = false;
    for (const node of document.querySelectorAll('#root, #linux-toolbar, #linux-view-review-banner')) {
      if (!background.has(node)) { background.set(node, node.getAttribute('aria-hidden')); node.setAttribute('aria-hidden', 'true'); }
    }
    render(); overlay.querySelector('[role="dialog"]').focus();
  }
  function renderBanner() {
    banner.replaceChildren(); banner.hidden = !reviews.length;
    for (const review of reviews) {
      const button = element('button', (review.phase === 'regenerating' ? 'View regeneration queued or running: ' : 'Views ready for review: ')+(review.title || 'Untitled cast'));
      button.type = 'button'; button.addEventListener('click', () => show(review.job_id)); banner.append(button);
    }
  }
  function render() {
    const review = reviews.find(item => item.job_id === currentId);
    if (!review) { if (currentId) close(); return; }
    const next = review.job_id+':'+review.revision+':'+busy;
    if (signature === next) return;
    signature = next;
    const hadFocus = overlay.contains(document.activeElement);
    overlay.querySelector('#lvr-job').textContent = review.title || 'Untitled cast';
    const regenerating = review.phase === 'regenerating';
    overlay.querySelector('#lvr-status').textContent = regenerating
      ? 'Regenerating '+(labels[review.regenerating_view] || 'one view').toLowerCase()+'. The previous image stays visible until its replacement is ready.'
      : review.views.filter(v => v.accepted).length+' of '+review.views.length+' alternate views approved. Click an image to enlarge it.';
    const error = overlay.querySelector('#lvr-error'); error.hidden = !(review.error || actionError); error.textContent = review.error || actionError;
    const cards = overlay.querySelector('#lvr-cards'); cards.replaceChildren();
    for (const item of [{name: 'front', accepted: true}, ...review.views]) {
      let approveButton;
      const card = element('article', undefined, item.accepted ? 'lvr-card lvr-approved' : 'lvr-card');
      card.append(element('h3', labels[item.name] || item.name));
      const enlarge = element('button', undefined, 'lvr-image'); enlarge.type = 'button'; enlarge.setAttribute('aria-label', 'Enlarge '+labels[item.name]);
      const image = element('img'); image.alt = labels[item.name]; enlarge.append(image); card.append(enlarge);
      enlarge.addEventListener('click', () => {
        if (!image.src) return;
        const zoom = overlay.querySelector('#lvr-zoom'); zoom.querySelector('img').src = image.src;
        zoom.querySelector('img').alt = image.alt; zoom.hidden = false;
        zoom.querySelector('button').focus();
      });
      card.append(element('p', item.name === 'front' ? 'Your selected reference' : item.accepted ? 'Approved' : 'Needs your approval', 'lvr-view-state'));
      if (item.name !== 'front') {
        const actions = element('div', undefined, 'lvr-actions');
        for (const [action, label] of [['approve', item.accepted ? 'Approved' : 'Approve view'], ['regenerate', 'Reject & regenerate']]) {
          const button = element('button', label); button.type = 'button';
          button.disabled = busy || regenerating || (action === 'approve' && item.accepted);
          if (action === 'approve' && !item.accepted) { approveButton = button; button.disabled = true; }
          button.addEventListener('click', () => act(action, item.name)); actions.append(button);
        }
        card.append(actions);
      }
      cards.append(card); loadImage(review, item.name, image, approveButton);
    }
    overlay.querySelector('[data-action="continue"]').disabled = busy || regenerating || !review.views.every(v => v.accepted);
    overlay.querySelector('[data-action="cancel"]').disabled = busy;
    if (hadFocus && !overlay.contains(document.activeElement)) overlay.querySelector('[role="dialog"]').focus({preventScroll:true});
  }
  async function refresh(autoOpen = true) {
    if (!connection()) return;
    const number = ++refreshNumber;
    const result = await api('');
    if (number < appliedRefresh) return;
    appliedRefresh = number; reviews = result.reviews;
    renderBanner();
    if (autoOpen && !currentId) {
      const fresh = reviews.find(review => !seen.has(review.job_id));
      if (fresh) show(fresh.job_id);
    }
    for (const review of reviews) seen.add(review.job_id);
    if (currentId) render();
  }
  async function act(action, view) {
    const review = reviews.find(item => item.job_id === currentId);
    if (!review || busy) return;
    actionError = ''; busy = true; render();
    try {
      await api('/'+review.job_id+'/'+action, {revision: review.revision, ...(view ? {view} : {})});
      await refresh(false);
    } catch (error) {
      // Refresh stale versions without turning a failed request into an implicit approval.
      await refresh(false).catch(() => {});
      actionError = error.message;
      signature = ''; // The next action always uses the refreshed revision.
    } finally { busy = false; render(); }
  }
  overlay.addEventListener('click', event => {
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'later') close();
    else if (action === 'refresh') { signature = ''; refresh(false).catch(error => { actionError = error.message; render(); }); }
    else if (action === 'unzoom') overlay.querySelector('#lvr-zoom').hidden = true;
    else if (action === 'continue' || action === 'cancel') act(action);
  });
  overlay.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (!overlay.querySelector('#lvr-zoom').hidden) overlay.querySelector('#lvr-zoom').hidden = true;
      else close();
      event.preventDefault();
    }
    if (event.key === 'Tab') {
      const scope = overlay.querySelector('#lvr-zoom').hidden ? overlay : overlay.querySelector('#lvr-zoom');
      const focusable = [...scope.querySelectorAll('button:not(:disabled)')].filter(node => node.offsetParent !== null);
      const first = focusable[0], last = focusable.at(-1);
      if (!overlay.contains(document.activeElement)) { (event.shiftKey ? last : first)?.focus(); event.preventDefault(); }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement.matches('[role="dialog"]'))) { last?.focus(); event.preventDefault(); }
      else if (!event.shiftKey && document.activeElement === last) { first?.focus(); event.preventDefault(); }
    }
  });
  document.addEventListener('focusin', event => {
    if (!overlay.hidden && !overlay.contains(event.target)) overlay.querySelector('[role="dialog"]').focus({preventScroll:true});
  });
  document.addEventListener('DOMContentLoaded', () => {
    document.body.append(banner, overlay);
    refresh().catch(() => {});
    setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 2000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh().catch(() => {}); });
  });
})();
