(() => {
  const entity = document.querySelector('#entity');
  const system = document.querySelector('#access');
  const refreshAccesses = document.querySelector('#refresh-accesses');
  let signature = '';
  let loadedEntity = '';

  const escapeText = value => String(value ?? '').replace(
    /[&<>"']/g,
    char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]),
  );

  function fillSystems(entities) {
    const selected = entities.find(item => item.id === entity.value);
    const previous = system.value;
    system.innerHTML = selected?.systems?.length
      ? selected.systems.map(item => `<option value="${item.access}">${escapeText(item.label)}</option>`).join('')
      : '<option value="">Selecione a entidade para consultar os sistemas</option>';
    system.disabled = !selected?.systems?.length;
    if ([...system.options].some(option => option.value === previous)) system.value = previous;
    system.dispatchEvent(new Event('change'));
  }

  async function loadSystems() {
    if (!entity.value) return;
    loadedEntity = entity.value;
    system.disabled = true;
    system.innerHTML = '<option>Consultando permissões...</option>';
    try {
      const response = await fetch('/api/systems', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({entity: entity.value}),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Não foi possível consultar os sistemas');
      signature = '';
      await refreshSource();
    } catch (error) {
      loadedEntity = '';
      system.innerHTML = `<option>${escapeText(error.message)}</option>`;
    }
  }

  async function refreshSource() {
    try {
      const response = await fetch('/api/state', {cache: 'no-store'});
      if (!response.ok) return;
      const state = await response.json();
      if (!state.authenticated && authenticated) await refresh();
      const entities = state.entities || [];
      const next = JSON.stringify({entities, preferred: state.preferredEntity});
      if (next === signature) return;
      signature = next;
      const previous = entity.value;
      entity.innerHTML = entities.length
        ? entities.map(item => `<option value="${escapeText(item.id)}" title="${escapeText(item.label)}">${escapeText(item.label)}</option>`).join('')
        : '<option value="">Autentique-se primeiro</option>';
      entity.disabled = !entities.length;
      if (entities.some(item => item.id === previous)) entity.value = previous;
      else if (entities.some(item => item.id === state.preferredEntity)) entity.value = state.preferredEntity;
      entity.title = entity.selectedOptions[0]?.textContent || '';
      fillSystems(entities);
      entity.onchange = () => {
        entity.title = entity.selectedOptions[0]?.textContent || '';
        fillSystems(entities);
        loadSystems();
      };
      if (entity.value && loadedEntity !== entity.value) loadSystems();
    } catch (_) {
      // A próxima atualização periódica tentará novamente.
    }
  }

  refreshAccesses.onclick = () => action(async signal => {
    const previousEntity = entity.value;
    const previousSystem = system.selectedOptions[0]?.textContent || '';
    invalidateAnalysis();
    await request('/api/accesses', {method: 'POST', signal});
    signature = '';
    loadedEntity = '';
    await refreshSource();
    if (previousEntity && entity.value === previousEntity && previousSystem) {
      const previousOption = [...system.options].find(option => option.textContent === previousSystem);
      if (previousOption) system.value = previousOption.value;
    }
    toast('A lista de entidades e sistemas foi atualizada.');
  });

  refreshSource();
  setInterval(refreshSource, 1000);
})();
