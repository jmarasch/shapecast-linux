/* Reversible job-list controls; assets and vendor records are never deleted. */
(() => {
  'use strict';
  const dialog = document.createElement('dialog'); dialog.id = 'linux-jobs';
  dialog.setAttribute('aria-labelledby', 'lj-title');
  dialog.innerHTML = `<header><h2 id="lj-title">Manage jobs</h2><button type="button" data-action="close">Close</button></header>
    <p>Clear jobs that have not started, or hide finished jobs from the lists. Generated files and library assets are kept.</p>
    <div class="lj-tools"><button type="button" data-action="clear" disabled>Clear waiting queue</button>
    <label><input type="checkbox" id="lj-hidden"> Show hidden jobs</label><button type="button" data-action="refresh">Refresh</button></div>
    <p id="lj-message" role="status" aria-live="polite"></p><div id="lj-rows"></div>
    <footer><button type="button" data-action="previous" disabled>Previous</button><span id="lj-page"></span><button type="button" data-action="next" disabled>Next</button></footer>`;
  document.body.append(dialog);
  let data = null, offset = 0, busy = false, changed = false, lastFocus;
  const hidden = dialog.querySelector('#lj-hidden');
  const message = dialog.querySelector('#lj-message');
  const node = (tag, text) => { const result = document.createElement(tag); result.textContent = text; return result; };
  function request(path, body) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest(); xhr.open(body === undefined ? 'GET' : 'POST', '/linux-jobs-api'+path);
      xhr.responseType = 'json'; xhr.timeout = 25000;
      xhr.setRequestHeader('Authorization', 'Bearer '+window.__SHAPECAST__.token);
      if (body !== undefined) xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 && xhr.response ? resolve(xhr.response)
        : reject(new Error(typeof xhr.response?.detail === 'string' ? xhr.response.detail : 'Could not update the job list. Try again.'));
      xhr.onerror = xhr.ontimeout = () => reject(new Error('Could not reach the local job service. Try again.'));
      xhr.send(body === undefined ? null : JSON.stringify(body));
    });
  }
  function render() {
    const rows = dialog.querySelector('#lj-rows'); rows.replaceChildren();
    if (!data.jobs.length) rows.append(node('p', hidden.checked ? 'No hidden jobs.' : 'No jobs to show.'));
    for (const job of data.jobs) {
      const row = document.createElement('article');
      const description = document.createElement('div');
      description.append(node('strong', job.title), node('small', job.status.replaceAll('_', ' ')+' · '+new Date(job.created_at).toLocaleString()));
      row.append(description);
      const action = job.hidden ? 'restore' : job.can_hide ? 'hide' : job.status === 'queued' ? 'cancel' : null;
      if (action) {
        const button = node('button', {restore:'Restore to lists', hide:'Hide', cancel:'Cancel waiting job'}[action]);
        button.type = 'button'; button.disabled = busy;
        button.addEventListener('click', () => perform(action, job)); row.append(button);
      } else row.append(node('small', 'Use cast controls to stop or finish this job.'));
      rows.append(row);
    }
    dialog.querySelector('[data-action="clear"]').textContent = 'Clear waiting queue ('+data.queued_ids.length+')';
    dialog.querySelector('[data-action="clear"]').disabled = busy || !data.queued_ids.length;
    dialog.querySelector('[data-action="previous"]').disabled = busy || offset === 0;
    dialog.querySelector('[data-action="next"]').disabled = busy || offset+data.jobs.length >= data.total;
    dialog.querySelector('#lj-page').textContent = data.total ? (offset+1)+'–'+(offset+data.jobs.length)+' of '+data.total : '0 jobs';
    dialog.querySelector('[data-action="refresh"]').disabled = hidden.disabled = busy;
  }
  async function load() {
    data = await request('?offset='+offset+'&hidden='+(hidden.checked ? 1 : 0));
    if (offset && !data.jobs.length) { offset = Math.max(0, offset-50); return load(); }
    render();
  }
  async function perform(action, job) {
    if (busy) return;
    if (action === 'clear' && !confirm('Cancel the '+data.queued_ids.length+' waiting jobs shown in this queue snapshot? Running jobs and casts waiting for your approval will continue unchanged. Files are kept.')) return;
    if (action === 'cancel' && !confirm('Cancel this waiting job? Its files will be kept.')) return;
    busy = true; render(); message.textContent = 'Updating jobs…';
    try {
      const result = await request(action === 'clear' ? '/clear' : '/'+job.id+'/'+action,
        action === 'clear' ? {job_ids: data.queued_ids} : {});
      changed = true;
      message.textContent = action === 'hide' ? 'Job hidden. Choose Show hidden jobs to restore it.'
        : action === 'restore' ? 'Job restored to the lists.'
        : result.changed+' waiting job(s) cancelled.'+(result.skipped ? ' '+result.skipped+' already started or changed and were left alone.' : '');
      await load();
    } catch (error) { message.textContent = error.message; }
    finally { busy = false; render(); }
  }
  async function refresh() {
    if (busy) return;
    busy = true; hidden.disabled = true; message.textContent = 'Loading jobs…';
    try { await load(); message.textContent = 'Running jobs and casts waiting for approval stay listed.'; }
    catch (error) { message.textContent = error.message; }
    finally { busy = false; hidden.disabled = false; if (data) render(); }
  }
  dialog.addEventListener('click', event => {
    const action = event.target.closest('[data-action]')?.dataset.action;
    if (action === 'close') { if (!busy) dialog.close(); }
    else if (action === 'clear') perform('clear');
    else if (action === 'refresh') refresh();
    else if ((action === 'next' || action === 'previous') && !busy) { offset += action === 'next' ? 50 : -50; refresh(); }
  });
  hidden.addEventListener('change', () => { offset = 0; refresh(); });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    // Refetch the original application's lists too; no generation or approval is submitted.
    if (changed) location.reload(); else lastFocus?.focus();
  });
  function mount() {
    const toolbar = document.querySelector('#linux-toolbar');
    if (!toolbar || !window.__SHAPECAST__?.token) { setTimeout(mount, 200); return; }
    const button = node('button', 'Manage jobs'); button.type = 'button'; button.id = 'linux-manage-jobs';
    button.addEventListener('click', () => { lastFocus = document.activeElement; dialog.showModal(); refresh(); });
    toolbar.insertBefore(button, toolbar.querySelector('a'));
  }
  mount();
})();
