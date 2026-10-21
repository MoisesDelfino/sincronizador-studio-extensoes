const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));
const kindLabel = kind => kind === 'JOB' ? 'SCRIPT' : kind;

let busy = false;
let authenticated = false;
let folderParent = '';
let changes = [];
let selectedChanges = new Set();
let currentPage = 1;
let pageSize = 20;
let toastTimer;
let actionController;
let folderController;
let currentStep = 1;
let analysisReady = false;

const stepDescriptions = {
  1: 'Entre com sua conta Betha para iniciar.',
  2: 'Selecione a entidade e o sistema de origem.',
  3: 'Escolha a pasta local e os tipos de artefato.',
  4: 'Revise as diferenças e sincronize os itens selecionados.'
};

function contextSelected() {
  return authenticated && Boolean($('#entity').value) && Boolean($('#access').value) && !$('#access').disabled;
}

function availableStep() {
  if (!authenticated) return 1;
  if (analysisReady) return 4;
  if (contextSelected()) return 3;
  return 2;
}

function updateWizard() {
  const maximum = availableStep();
  if (currentStep > maximum) currentStep = maximum;
  document.querySelectorAll('[data-panel]').forEach(panel => {
    panel.hidden = Number(panel.dataset.panel) !== currentStep;
  });
  document.querySelectorAll('.wizard-step').forEach(step => {
    const number = Number(step.dataset.step);
    step.disabled = busy || number > maximum;
    step.classList.toggle('active', number === currentStep);
    step.classList.toggle('complete', number < currentStep || number < maximum);
    step.setAttribute('aria-current', number === currentStep ? 'step' : 'false');
  });
  $('#step-description').textContent = stepDescriptions[currentStep];
  $('#context-next').disabled = busy || !contextSelected();
  updateAnalyzeAvailability();
}

function goToStep(step) {
  if (step > availableStep()) return;
  currentStep = step;
  updateWizard();
  document.querySelector(`[data-panel="${step}"]`)?.querySelector('select, input, button:not(:disabled)')?.focus();
  window.scrollTo({top: 0, behavior: 'smooth'});
}

function invalidateAnalysis() {
  if (!analysisReady && !changes.length) return;
  analysisReady = false;
  changes = [];
  selectedChanges.clear();
  currentPage = 1;
  renderChanges();
  updateWizard();
}

function toast(message) {
  const element = $('#toast');
  clearTimeout(toastTimer);
  element.className = 'toast';
  element.textContent = message;
  element.classList.add('show');
  toastTimer = setTimeout(() => element.classList.remove('show'), 3500);
}

function synchronizationToast(result) {
  const element = $('#toast');
  const items = Array.isArray(result.items) ? result.items : [];
  const visible = items.slice(0, 5);
  const remaining = Math.max(0, items.length - visible.length);
  clearTimeout(toastTimer);
  element.className = 'toast sync-toast';
  element.innerHTML = `
    <div class="toast-head">
      <span class="toast-success" aria-hidden="true">✓</span>
      <div><strong>Sincronização concluída</strong><small>${result.written} arquivo(s) gravado(s)</small></div>
      <button type="button" class="toast-close" aria-label="Fechar notificação">×</button>
    </div>
    <div class="toast-totals">
      <span><b>${result.created || 0}</b> criado(s)</span>
      <span><b>${result.updated || 0}</b> atualizado(s)</span>
    </div>
    <ul class="toast-items">${visible.map(item => `
      <li title="${esc(item.path)}">
        <span class="toast-action ${esc(item.action)}">${item.action === 'CRIAR' ? 'CRIADO' : 'ATUALIZADO'}</span>
        <div><strong>${esc(item.title)}</strong><small>${esc(kindLabel(item.kind))}</small></div>
      </li>`).join('')}
    </ul>
    ${remaining ? `<p class="toast-more">e mais ${remaining} arquivo(s).</p>` : ''}`;
  element.querySelector('.toast-close').onclick = () => element.classList.remove('show');
  element.classList.add('show');
  toastTimer = setTimeout(() => element.classList.remove('show'), 9000);
}

function confirmAction({eyebrow, title, description, acceptLabel, icon = '✓', count = null}) {
  return new Promise(resolve => {
    const modal = $('#confirm-modal');
    const accept = $('#confirm-accept');
    const cancel = $('#confirm-cancel');
    const summary = $('#confirm-summary');
    const previousFocus = document.activeElement;
    $('#confirm-eyebrow').textContent = eyebrow;
    $('#confirm-title').textContent = title;
    $('#confirm-description').textContent = description;
    $('#confirm-icon').textContent = icon;
    accept.textContent = acceptLabel;
    summary.hidden = count === null;
    if (count !== null) $('#confirm-count').textContent = count;
    modal.hidden = false;
    document.body.classList.add('modal-open');

    const finish = confirmed => {
      modal.hidden = true;
      document.body.classList.remove('modal-open');
      document.removeEventListener('keydown', onKeydown);
      previousFocus?.focus();
      resolve(confirmed);
    };
    const onKeydown = event => {
      if (event.key === 'Escape') finish(false);
    };
    accept.onclick = () => finish(true);
    cancel.onclick = () => finish(false);
    modal.onclick = event => { if (event.target === modal) finish(false); };
    document.addEventListener('keydown', onKeydown);
    requestAnimationFrame(() => accept.focus());
  });
}

function confirmSynchronization(count) {
  return confirmAction({
    eyebrow: 'CONFIRMAR SINCRONIZAÇÃO',
    title: 'Sincronizar arquivos selecionados?',
    description: 'Os arquivos locais serão criados ou atualizados com o conteúdo do Studio Extensões.',
    acceptLabel: 'Sincronizar agora →',
    count
  });
}

async function request(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'A operação falhou');
  return data;
}

function searchedChanges() {
  const query = $('#script-search').value.trim().toLocaleLowerCase('pt-BR');
  if (!query) return changes;
  return changes.filter(change => [change.title, kindLabel(change.kind), change.message, change.path]
    .some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(query)));
}

function selectedStatuses() {
  const statuses = new Set(
    [...document.querySelectorAll('.status-filter:checked')]
      .flatMap(input => input.value.split(','))
  );
  return statuses;
}

function currentPageSourceChanges() {
  const searched = searchedChanges();
  const pageCount = Math.max(1, Math.ceil(searched.length / pageSize));
  currentPage = Math.min(Math.max(1, currentPage), pageCount);
  const start = (currentPage - 1) * pageSize;
  return searched.slice(start, start + pageSize);
}

function currentPageChanges() {
  const statuses = selectedStatuses();
  return currentPageSourceChanges().filter(change => statuses.has(change.status));
}

function showLoading(visible, message = 'Aguarde um momento...') {
  $('#loading').hidden = !visible;
  $('#loading-message').textContent = message;
  $('#loading-cancel').disabled = !visible || !actionController;
}

function updateGuidance() {
  updateWizard();
}

function updateSelection() {
  const validIndexes = new Set(changes.filter(change => change.actionable).map(change => change.index));
  selectedChanges = new Set([...selectedChanges].filter(index => validIndexes.has(index)));
  const pageActionable = currentPageChanges().filter(change => change.actionable);
  const selectedOnPage = pageActionable.filter(change => selectedChanges.has(change.index)).length;
  const toggle = $('#select-page');
  toggle.checked = pageActionable.length > 0 && selectedOnPage === pageActionable.length;
  toggle.indeterminate = selectedOnPage > 0 && selectedOnPage < pageActionable.length;
  const allActionable = changes.filter(change => change.actionable);
  const allLoaded = changes.length > 0 && changes.every(change => change.loaded);
  const allSelected = allLoaded && allActionable.length > 0 && allActionable.every(change => selectedChanges.has(change.index));
  $('#select-all').textContent = allSelected ? 'Limpar seleção' : `Selecionar todos (${changes.length})`;
  $('#selection-count').textContent = `${selectedChanges.size} selecionado(s)`;
  $('#sync').disabled = busy || selectedChanges.size === 0;
  updateGuidance();
}

function updateAnalyzeAvailability() {
  $('#analyze').disabled = busy || !contextSelected() || !$('#folder').value.trim();
}

function renderChanges() {
  const searched = searchedChanges();
  const pageItems = currentPageSourceChanges();
  const rows = currentPageChanges();
  let emptyMessage = 'Analise o repositório para visualizar as diferenças.';
  if (changes.length && !searched.length) emptyMessage = 'Nenhum script corresponde à pesquisa.';
  else if (pageItems.length && !rows.length) emptyMessage = 'Nenhum item desta página corresponde às situações selecionadas.';
  $('#rows').innerHTML = rows.length ? rows.map(change => {
    const detail = change.message || change.path || '';
    const displayedKind = kindLabel(change.kind);
    const problem = change.status === 'CONFLITO' || change.status === 'ERRO';
    const checkbox = change.actionable
      ? `<input class="change-check" type="checkbox" data-index="${change.index}" ${selectedChanges.has(change.index) ? 'checked' : ''} aria-label="Selecionar ${esc(change.title)}">`
      : '<span class="not-actionable" title="Este item precisa ser revisado">—</span>';
    return `<tr class="${problem ? 'problem-row' : ''}">
      <td class="select-column">${checkbox}</td>
      <td class="status-cell"><span class="badge ${esc(change.status)}">${esc(change.status)}</span></td>
      <td class="type-cell" title="${esc(displayedKind)}">${esc(displayedKind)}</td>
      <td class="file-name" title="${esc(change.title)}">
        <span class="file-title">${esc(change.title)}</span>
        <small class="mobile-kind">${esc(displayedKind)}</small>
        ${detail ? `<small class="mobile-detail ${problem ? 'problem-detail' : ''}">${esc(detail)}</small>` : ''}
      </td>
      <td class="detail ${problem ? 'problem-detail' : ''}">${esc(detail)}</td>
    </tr>`;
  }).join('') : `<tr class="empty"><td colspan="5">${emptyMessage}</td></tr>`;
  document.querySelectorAll('.change-check').forEach(checkbox => {
    checkbox.onchange = () => {
      const index = Number(checkbox.dataset.index);
      checkbox.checked ? selectedChanges.add(index) : selectedChanges.delete(index);
      updateSelection();
    };
  });
  const pageCount = Math.max(1, Math.ceil(searched.length / pageSize));
  const first = searched.length ? (currentPage - 1) * pageSize + 1 : 0;
  const last = Math.min(currentPage * pageSize, searched.length);
  const shown = rows.length !== pageItems.length ? ` • ${rows.length} exibido(s)` : '';
  $('#page-summary').textContent = searched.length ? `${first}–${last} de ${searched.length} item(ns)${shown}` : 'Nenhum item';
  $('#page-indicator').textContent = `Página ${currentPage} de ${pageCount}`;
  $('#first-page').disabled = busy || currentPage <= 1;
  $('#previous-page').disabled = busy || currentPage <= 1;
  $('#next-page').disabled = busy || currentPage >= pageCount;
  $('#last-page').disabled = busy || currentPage >= pageCount;
  updateSelection();
}

async function loadChanges(clearSelection = false, resetPage = true) {
  changes = await request('/api/changes');
  if (clearSelection) selectedChanges.clear();
  if (resetPage) currentPage = 1;
  renderChanges();
}

async function loadRows(rows) {
  const missing = rows.filter(change => !change.loaded).map(change => change.index);
  if (!missing.length) return;
  await action(async signal => {
    await request('/api/page', {
      method: 'POST', signal, body: JSON.stringify({changes: missing})
    });
    await loadChanges(false, false);
  });
}

async function loadCurrentPage() {
  renderChanges();
  await loadRows(currentPageSourceChanges());
}

async function refresh() {
  const state = await request('/api/state');
  busy = state.busy;
  authenticated = state.authenticated;
  $('#status').textContent = state.status;
  $('#account').textContent = state.authenticated ? state.user : 'Nenhuma sessão conectada';
  $('#login').textContent = state.authenticated ? 'Trocar conta ↗' : 'Entrar no Studio Extensões ↗';
  $('#create').textContent = state.counts.CRIAR;
  $('#update').textContent = state.counts.ATUALIZAR;
  $('#unchanged').textContent = state.counts.INALTERADO;
  $('#pending').textContent = state.counts.PENDENTE || 0;
  $('#problems').textContent = state.counts.CONFLITO + state.counts.ERRO;
  document.querySelectorAll('button').forEach(button => button.disabled = busy);
  $('#undo').disabled = busy || !state.canUndo;
  showLoading(busy, state.status);
  renderChanges();
  updateWizard();
}

async function waitUntilIdle() {
  for (let attempt = 0; attempt < 100; attempt++) {
    const state = await request('/api/state');
    if (!state.busy) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
}

async function action(callback) {
  busy = true;
  actionController = new AbortController();
  document.querySelectorAll('button').forEach(button => button.disabled = true);
  showLoading(true, 'Preparando a operação...');
  try { await callback(actionController.signal); }
  catch (error) { if (error.name !== 'AbortError') toast(error.message); }
  finally {
    if (actionController.signal.aborted) await waitUntilIdle();
    actionController = undefined;
    busy = false;
    showLoading(false);
    await refresh();
  }
}

$('#loading-cancel').onclick = async () => {
  if (!actionController) return;
  actionController.abort();
  $('#loading-cancel').disabled = true;
  $('#loading-message').textContent = 'Cancelando operação...';
  try { await request('/api/cancel', {method: 'POST'}); }
  catch (_) { toast('A aplicação foi atualizada. Feche-a e abra novamente para habilitar o cancelamento.'); }
};

$('#login').onclick = () => action(async signal => {
  await request('/api/authenticate', {
    method: 'POST', signal, body: JSON.stringify({resetSession: authenticated})
  });
  authenticated = true;
  analysisReady = false;
  currentStep = 2;
});

async function browseFolder(path = '') {
  folderController?.abort();
  folderController = new AbortController();
  const message = $('#folder-message');
  message.textContent = 'Carregando...';
  try {
    const data = await request('/api/folders', {method: 'POST', signal: folderController.signal, body: JSON.stringify({path})});
    folderParent = data.parent;
    $('#folder-current').value = data.path;
    $('#folder-up').disabled = !data.parent;
    $('#folder-list').innerHTML = data.directories.length
      ? data.directories.map(item => `<button data-path="${esc(item.path)}"><span>📁</span>${esc(item.name)}</button>`).join('')
      : '<p>Esta pasta não contém subpastas.</p>';
    $('#folder-list').querySelectorAll('button').forEach(button => button.onclick = () => browseFolder(button.dataset.path));
    message.textContent = `${data.directories.length} pasta(s)`;
  } catch (error) { if (error.name !== 'AbortError') message.textContent = error.message; }
}

$('#choose').onclick = () => {
  $('#folder-modal').hidden = false;
  document.body.classList.add('modal-open');
  browseFolder($('#folder').value);
};
$('#folder-cancel').onclick = () => {
  folderController?.abort();
  $('#folder-modal').hidden = true;
  document.body.classList.remove('modal-open');
};
$('#folder-up').onclick = () => folderParent && browseFolder(folderParent);
$('#folder-go').onclick = () => browseFolder($('#folder-current').value);
$('#folder-current').onkeydown = event => { if (event.key === 'Enter') browseFolder(event.currentTarget.value); };
$('#folder-select').onclick = () => {
  const changed = $('#folder').value !== $('#folder-current').value;
  $('#folder').value = $('#folder-current').value;
  $('#folder-modal').hidden = true;
  document.body.classList.remove('modal-open');
  if (changed) invalidateAnalysis();
  updateWizard();
};

document.querySelectorAll('.wizard-step').forEach(step => {
  step.onclick = () => goToStep(Number(step.dataset.step));
});
document.querySelectorAll('.wizard-back').forEach(button => {
  button.onclick = () => goToStep(Number(button.dataset.target));
});
$('#context-next').onclick = () => goToStep(3);
$('#change-context').onclick = () => goToStep(2);
$('#entity').addEventListener('change', () => {
  invalidateAnalysis();
  updateWizard();
});
$('#access').addEventListener('change', () => {
  invalidateAnalysis();
  updateWizard();
});

let searchTimer;
$('#script-search').oninput = () => {
  currentPage = 1;
  renderChanges();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadCurrentPage, 250);
};
document.querySelectorAll('.status-filter').forEach(input => {
  input.onchange = () => {
    renderChanges();
  };
});
$('#select-page').onchange = event => {
  currentPageChanges().filter(change => change.actionable).forEach(change => {
    event.currentTarget.checked ? selectedChanges.add(change.index) : selectedChanges.delete(change.index);
  });
  renderChanges();
};
$('#select-all').onclick = async () => {
  const loadedActionable = changes.filter(change => change.actionable);
  const allLoaded = changes.length > 0 && changes.every(change => change.loaded);
  const allSelected = allLoaded && loadedActionable.length > 0
    && loadedActionable.every(change => selectedChanges.has(change.index));
  if (!allSelected) await loadRows(changes);
  const actionable = changes.filter(change => change.actionable);
  actionable.forEach(change => allSelected ? selectedChanges.delete(change.index) : selectedChanges.add(change.index));
  renderChanges();
};
$('#page-size').onchange = async event => {
  pageSize = Number(event.currentTarget.value); currentPage = 1; await loadCurrentPage();
};
$('#first-page').onclick = async () => {
  if (currentPage > 1) { currentPage = 1; await loadCurrentPage(); }
};
$('#previous-page').onclick = async () => {
  if (currentPage > 1) { currentPage--; await loadCurrentPage(); }
};
$('#next-page').onclick = async () => {
  const pageCount = Math.max(1, Math.ceil(searchedChanges().length / pageSize));
  if (currentPage < pageCount) { currentPage++; await loadCurrentPage(); }
};
$('#last-page').onclick = async () => {
  const pageCount = Math.max(1, Math.ceil(searchedChanges().length / pageSize));
  if (currentPage < pageCount) { currentPage = pageCount; await loadCurrentPage(); }
};

$('#analyze').onclick = () => action(async signal => {
  await request('/api/analyze', {
    method: 'POST',
    signal,
    body: JSON.stringify({
      access: +$('#access').value,
      folder: $('#folder').value,
      job: $('#job').checked,
      component: $('#component').checked,
      critique: $('#critique').checked,
      dynamicSource: $('#dynamic-source').checked,
      report: $('#report').checked
    })
  });
  await loadChanges(true);
  const firstPage = currentPageSourceChanges();
  await request('/api/page', {
    method: 'POST', signal, body: JSON.stringify({changes: firstPage.map(change => change.index)})
  });
  await loadChanges(false, false);
  analysisReady = true;
  currentStep = 4;
  updateWizard();
});

$('#sync').onclick = async () => {
  if (!selectedChanges.size) return toast('Selecione ao menos um script.');
  if (!await confirmSynchronization(selectedChanges.size)) return;
  await action(async signal => {
    const data = await request('/api/apply', {
      method: 'POST', signal, body: JSON.stringify({changes: [...selectedChanges]})
    });
    synchronizationToast(data);
    selectedChanges.clear();
    await loadChanges();
  });
};

$('#undo').onclick = async () => {
  if (!await confirmAction({
    eyebrow: 'CONFIRMAR RESTAURAÇÃO',
    title: 'Desfazer a última sincronização?',
    description: 'Os arquivos alterados na última sincronização serão substituídos pelas versões anteriores.',
    acceptLabel: 'Desfazer sincronização',
    icon: '↶'
  })) return;
  await action(async signal => {
    const data = await request('/api/undo', {method: 'POST', signal});
    toast(`Última sincronização desfeita: ${data.restored} arquivo(s) restaurado(s).`);
    selectedChanges.clear();
    await loadChanges(true);
  });
};

$('#close').onclick = async () => {
  await request('/api/shutdown', {method: 'POST'});
  document.body.innerHTML = '<main><section class="page-heading"><div><span class="eyebrow">STUDIO EXTENSÕES</span><h1>Aplicação encerrada</h1><p>Esta aba já pode ser fechada.</p></div></section></main>';
};

refresh();
setInterval(() => { if (busy) refresh(); }, 900);
