/* Queue-page record cleanup. Pending and active jobs are never cleared. */
(() => {
  'use strict';
  const finished = new Set(['complete', 'failed', 'cancelled']);
  let busy = false, lastBatch = sessionStorage.getItem('linux-queue-undo'), notice = '';
  const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  function request(path, body) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest(); xhr.open('POST', '/linux-jobs-api'+path);
      xhr.responseType = 'json'; xhr.timeout = 25000;
      xhr.setRequestHeader('Authorization', 'Bearer '+window.__SHAPECAST__.token);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 && xhr.response ? resolve(xhr.response)
        : reject(new Error(typeof xhr.response?.detail === 'string' ? xhr.response.detail : 'Could not clear the record. Try again.'));
      xhr.onerror = xhr.ontimeout = () => reject(new Error('Could not reach the local queue service. Try again.'));
      xhr.send(JSON.stringify(body));
    });
  }
  function button(text, title, action, cls) {
    const result = document.createElement('button'); result.type = 'button'; result.textContent = text;
    result.title = title; result.className = cls; result.addEventListener('click', event => {
      event.preventDefault(); event.stopPropagation(); action();
    });
    return result;
  }
  async function clear(id) {
    if (busy || !window.__SHAPECAST__?.token) return;
    busy = true; notice = 'Clearing finished records…'; mount();
    try {
      const result = await request(id ? '/'+id+'/dismiss' : '/clear-finished', {});
      if (result.changed) {
        lastBatch = result.batch_id; sessionStorage.setItem('linux-queue-undo', lastBatch);
        document.querySelectorAll('[data-linux-queue-job]').forEach(row => {
          if ((!id || row.dataset.linuxQueueJob === id) && finished.has(row.dataset.linuxQueueStatus))
            row.classList.add('linux-queue-cleared');
        });
      }
      notice = result.changed+' finished record'+(result.changed === 1 ? '' : 's')+' cleared. Files are kept.';
    } catch (error) { notice = error.message; }
    finally { busy = false; mount(); }
  }
  async function undo() {
    if (busy || !lastBatch) return;
    busy = true; notice = 'Restoring records…'; mount();
    try {
      const result = await request('/restore-cleared', {batch_id:lastBatch});
      lastBatch = null; sessionStorage.removeItem('linux-queue-undo');
      document.querySelectorAll('.linux-queue-cleared').forEach(row => row.classList.remove('linux-queue-cleared'));
      notice = result.changed+' record'+(result.changed === 1 ? '' : 's')+' restored.';
    } catch (error) { notice = error.message; }
    finally { busy = false; mount(); }
  }
  function mount() {
    const page = document.querySelector('[data-linux-queue-page]');
    if (!page) return;
    const header = page.firstElementChild;
    let controls = page.querySelector('.linux-queue-controls');
    if (!controls) {
      controls = document.createElement('div'); controls.className = 'linux-queue-controls';
      const all = button('Clear all', 'Clear finished records only. Active and pending jobs stay listed.', () => clear(), 'linux-queue-clear-all');
      const restore = button('Undo clear', 'Restore the last records cleared from this Queue page.', undo, 'linux-queue-undo');
      const status = document.createElement('span'); status.className = 'linux-queue-notice';
      status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
      controls.append(all, restore, status); header.insertAdjacentElement('afterend', controls);
    }
    page.querySelectorAll('[data-linux-queue-job]').forEach(row => {
      const id = row.dataset.linuxQueueJob;
      const eligible = uuid.test(id || '') && finished.has(row.dataset.linuxQueueStatus);
      let remove = row.querySelector('.linux-queue-dismiss');
      if (!eligible) { remove?.remove(); return; }
      if (!remove) {
        remove = button('×', 'Clear this finished record from the Queue list.', () => clear(row.dataset.linuxQueueJob), 'linux-queue-dismiss');
        const label = row.querySelector('button')?.textContent || 'finished job';
        remove.setAttribute('aria-label', 'Clear finished record: '+label);
        row.prepend(remove);
      }
      remove.disabled = busy;
    });
    controls.querySelector('.linux-queue-clear-all').disabled = busy || !Array.from(page.querySelectorAll('[data-linux-queue-job]'))
      .some(row => finished.has(row.dataset.linuxQueueStatus) && !row.classList.contains('linux-queue-cleared'));
    const restore = controls.querySelector('.linux-queue-undo'); restore.hidden = !lastBatch; restore.disabled = busy;
    const status = controls.querySelector('.linux-queue-notice'); if (status.textContent !== notice) status.textContent = notice;
  }
  let scheduled = false;
  new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true; requestAnimationFrame(() => { scheduled = false; mount(); });
  }).observe(document.getElementById('root'), {childList:true, subtree:true});
  mount();
})();
