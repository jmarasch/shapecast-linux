/* Linux-only update controls; the vendor interface remains unchanged on disk. */
(() => {
  'use strict';
  const init = () => {
    const connection = window.__SHAPECAST__;
    if (!connection) return;
    let state = null, error = '', pending = false;
    const element = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const button = (label, action, secondary = false) => {
      const node = element('button', label, secondary ? 'lu-button lu-secondary' : 'lu-button');
      node.dataset.luFocus = label;
      node.type = 'button'; node.addEventListener('click', action); return node;
    };
    const bytes = value => {
      if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`;
      if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
      return `${value || 0} bytes`;
    };
    const api = async (path = '', method = 'GET', body) => {
      const response = await fetch(`${connection.baseUrl}/v1/linux-updates${path}`, {
        method, headers: {Authorization: `Bearer ${connection.token}`, ...(body ? {'Content-Type': 'application/json'} : {})},
        ...(body ? {body: JSON.stringify(body)} : {})
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(typeof result.detail === 'string' ? result.detail : 'The update request could not be completed.');
      }
      return response.json();
    };
    const banner = element('section', '', 'lu-banner');
    banner.setAttribute('aria-label', 'Update notice'); banner.hidden = true;
    document.getElementById('linux-toolbar').after(banner);
    const toolbar = button('Updates', () => open(), true);
    toolbar.id = 'linux-updates-open';
    document.getElementById('linux-setup').before(toolbar);
    const dialog = element('dialog', '', 'lu-dialog');
    dialog.setAttribute('aria-label', 'Software and model updates');
    const header = element('header', '', 'lu-dialog-header');
    header.append(element('h2', 'Software and model updates'), button('Close', () => dialog.close(), true));
    const content = element('div', '', 'lu-content');
    dialog.append(header, content); document.body.append(dialog);

    async function refresh() {
      try {
        const next = await api();
        const changed = JSON.stringify(next) !== JSON.stringify(state) || !!error;
        state = next; error = ''; if (changed) render();
      }
      catch (failure) { error = failure.message; if (dialog.open) renderPanel(); }
    }
    async function action(path, body) {
      if (pending) return;
      pending = true; error = ''; renderPanel();
      try { state = await api(path, 'POST', body); }
      catch (failure) { error = failure.message; }
      finally { pending = false; render(); }
    }
    function open() {
      renderPanel(); if (!dialog.open) dialog.showModal(); refresh();
    }
    function noticeKey() {
      const operation = state?.operation;
      return `${state?.fingerprint}:${operation?.state}:${operation?.fingerprint || operation?.message || ''}`;
    }
    function render() {
      if (!state) return;
      const updates = state.components.filter(item => item.available);
      toolbar.textContent = updates.length ? `Updates (${updates.length})` : 'Updates';
      const operation = state.operation || {};
      const working = ['downloading', 'applying'].includes(operation.state);
      const noteworthy = ['ready', 'done', 'error', 'paused'].includes(operation.state);
      const hidden = sessionStorage.getItem('shapecast.linux.updateNotice') === noticeKey();
      banner.hidden = !(working || (!hidden && (updates.length || noteworthy)));
      banner.replaceChildren();
      if (!banner.hidden) {
        let message = updates.length ? `Updates available: ${updates.map(item => item.kind === 'software' ? `Shapecast ${item.version}` : item.title).join(', ')}.` : '';
        if (working) message = operation.message || message;
        else if (noteworthy && operation.message) message = `${operation.message}${message ? ` ${message}` : ''}`;
        const text = element('span', message, 'lu-banner-message');
        text.setAttribute('role', 'status');
        banner.append(text, button(working ? 'View progress' : 'Review updates', open));
        if (!working) banner.append(button('Later', () => {
          sessionStorage.setItem('shapecast.linux.updateNotice', noticeKey()); render();
        }, true));
      }
      if (dialog.open) renderPanel();
    }
    function renderPanel() {
      const active = document.activeElement;
      const focusKey = content.contains(active) ? active?.dataset.luFocus : null;
      const scrollTop = dialog.scrollTop;
      content.replaceChildren();
      if (error) { const alert = element('p', error, 'lu-error'); alert.setAttribute('role', 'alert'); content.append(alert); }
      const top = element('div', '', 'lu-controls');
      const check = button(state?.checking ? 'Checking…' : 'Check now', () => action('/check'));
      check.disabled = pending || !!state?.checking; top.append(check);
      const preference = element('label', '', 'lu-preference');
      const automatic = element('input'); automatic.type = 'checkbox'; automatic.checked = state?.auto_check ?? true;
      automatic.dataset.luFocus = 'automatic-checks';
      automatic.disabled = pending;
      automatic.addEventListener('change', async () => {
        try { state = await api('/preferences', 'PUT', {auto_check: automatic.checked}); error = ''; }
        catch (failure) { error = failure.message; }
        renderPanel();
      });
      preference.append(automatic, document.createTextNode('Check automatically at startup and every six hours'));
      top.append(preference); content.append(top);
      if (!state) { content.append(element('p', 'Connecting to the update checker…')); return; }
      if (state.checked_at) content.append(element('p', `Last check: ${new Date(state.checked_at).toLocaleString()}`, 'lu-muted'));
      if (state.check_errors.length) content.append(element('p', 'Some update checks could not finish. Previously found updates are kept; try Check now again later.', 'lu-warning'));
      if (state.checked_at && state.components.length && !state.checking && !state.available && !state.check_errors.length) content.append(element('p', 'Your installed software and model files are current.', 'lu-success'));
      const operation = state.operation || {};
      if (operation.state) {
        const progressBox = element('section', '', 'lu-operation');
        progressBox.setAttribute('aria-label', 'Update progress');
        progressBox.append(element('p', operation.message || 'Preparing the update…'));
        if (operation.total_bytes && ['downloading', 'paused', 'ready'].includes(operation.state)) {
          const progress = element('progress'); progress.max = operation.total_bytes; progress.value = operation.done_bytes || 0;
          progressBox.append(progress, element('p', `${bytes(operation.done_bytes)} / ${bytes(operation.total_bytes)}`, 'lu-muted'));
        }
        if (operation.state === 'downloading') progressBox.append(button('Pause download', () => action('/pause'), true));
        content.append(progressBox);
      }
      for (const item of state.components) {
        const card = element('section', '', 'lu-card');
        card.append(element('h3', item.title));
        if (item.kind === 'software') {
          card.append(element('p', item.available ? `${item.current} → ${item.version}${item.released ? ` · Released ${item.released}` : ''}` : `Installed version: ${item.current}`, item.available ? '' : 'lu-muted'));
        } else {
          card.append(element('p', item.available ? `${item.changed_files} changed file${item.changed_files === 1 ? '' : 's'} · ${bytes(item.download_bytes)}${item.version ? ` · Pack ${item.version}` : ''}` : 'No model changes found.', item.available ? '' : 'lu-muted'));
        }
        if (item.failed_check) card.append(element('p', 'This feed was unavailable during the last check.', 'lu-warning'));
        if (item.kind === 'software') card.append(element('p', 'Downloads are kept separate. This Windows installer needs a Linux compatibility review before it can replace the working application.', 'lu-muted'));
        else if (item.read_only) card.append(element('p', 'These models are shared read-only with your working installation. Checks and staged downloads work here; applying an update requires a separate private model copy.', 'lu-muted'));
        else if (item.compatibility_required) card.append(element('p', 'This pack also changes model code. Download it for review; installation needs a Linux compatibility check.', 'lu-warning'));
        else if (item.available) card.append(element('p', 'Only changed model files are downloaded. Applying keeps a backup so you can restore the previous models.', 'lu-muted'));
        const matches = operation.component === item.id && operation.fingerprint === item.fingerprint;
        if (item.available && !(matches && operation.state === 'ready')) {
          const download = button(matches && ['paused', 'error'].includes(operation.state) ? 'Resume download' : item.kind === 'software' ? 'Download software update' : 'Download model update', () => action('/download', {component: item.id}));
          download.dataset.luFocus = `download-${item.id}`;
          download.disabled = pending || ['downloading', 'applying'].includes(operation.state); card.append(download);
        }
        if (matches && operation.state === 'ready') {
          if (item.kind === 'software') {
            const save = button('Save verified installer…', async () => {
              try {
                const response = await fetch(`${connection.baseUrl}/v1/linux-updates/installer`, {headers: {Authorization: `Bearer ${connection.token}`}});
                if (!response.ok) throw new Error('The installer could not be read.');
                const url = URL.createObjectURL(await response.blob());
                const link = element('a'); link.href = url; link.download = `Shapecast-Setup-${item.version}.exe`; link.click();
                setTimeout(() => URL.revokeObjectURL(url), 10000);
              } catch (failure) { error = failure.message; renderPanel(); }
            }); card.append(save);
            card.append(element('p', 'Downloaded and verified. Your current Linux installation is still active.', 'lu-success'));
          } else if (!item.compatibility_required && !item.read_only) {
            const apply = button('Apply model update', () => action('/apply'));
            apply.disabled = pending || state.busy; card.append(apply);
            if (state.busy) card.append(element('p', 'Finish or cancel current casts before applying.', 'lu-warning'));
          }
        }
        content.append(card);
      }
      const footer = element('section', '', 'lu-card');
      footer.append(element('h3', 'Linux launcher'), element('p', state.linux_launcher, 'lu-muted'));
      if (state.rollback_available) {
        const undo = button('Restore previous models', () => action('/rollback'), true);
        undo.disabled = pending || state.busy || ['downloading', 'applying'].includes(operation.state);
        footer.append(undo);
      }
      content.append(footer, element('p', 'Update checks request public release and model manifests. Your licence, machine ID and library are not sent. Downloads and installation start only when you choose them.', 'lu-muted'));
      if (focusKey) [...content.querySelectorAll('[data-lu-focus]')].find(node => node.dataset.luFocus === focusKey)?.focus({preventScroll:true});
      dialog.scrollTop = scrollTop;
    }
    refresh(); setInterval(refresh, 5000);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
