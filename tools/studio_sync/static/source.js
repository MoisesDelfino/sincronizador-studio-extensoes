(() => {
  const entity = document.querySelector('#entity');
  const entityTrigger = document.querySelector('#entity-trigger');
  const entityTriggerLabel = document.querySelector('#entity-trigger-label');
  const entityTriggerTag = document.querySelector('#entity-trigger-tag');
  const entityMenu = document.querySelector('#entity-menu');
  const system = document.querySelector('#access');
  const refreshAccesses = document.querySelector('#refresh-accesses');
  let signature = '';
  let loadedEntity = '';

  function closeEntityMenu() {
    entityMenu.hidden = true;
    entityTrigger.setAttribute('aria-expanded', 'false');
  }

  function updateEntityTrigger(entities) {
    const selected = entities.find(item => item.id === entity.value);
    entityTriggerLabel.textContent = selected?.label || 'Selecione uma entidade';
    entityTriggerTag.hidden = !selected?.orchestrator;
    entityTrigger.title = selected?.label || '';
    entityMenu.querySelectorAll('[role="option"]').forEach(option => {
      const active = option.dataset.id === entity.value;
      option.classList.toggle('selected', active);
      option.setAttribute('aria-selected', String(active));
    });
  }

  function selectEntity(id, entities) {
    if (!entities.some(item => item.id === id)) return;
    entity.value = id;
    updateEntityTrigger(entities);
    fillSystems(entities);
    closeEntityMenu();
    loadSystems();
  }

  function renderEntityMenu(entities) {
    entityMenu.innerHTML = entities.map(item => `
      <button class="entity-option" type="button" role="option" data-id="${escapeText(item.id)}" aria-selected="false">
        <span>${escapeText(item.label)}</span>
        ${item.orchestrator ? '<span class="entity-access-tag">Orquestrador</span>' : ''}
      </button>`).join('');
    entityMenu.querySelectorAll('[role="option"]').forEach(option => {
      option.onclick = () => selectEntity(option.dataset.id, entities);
    });
    updateEntityTrigger(entities);
  }

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
        ? entities.map(item => {
          const tag = item.orchestrator ? '  [Orquestrador]' : '';
          return `<option value="${escapeText(item.id)}" title="${escapeText(item.label + tag)}">${escapeText(item.label + tag)}</option>`;
        }).join('')
        : '<option value="">Autentique-se primeiro</option>';
      entity.disabled = !entities.length;
      entityTrigger.disabled = !entities.length;
      if (entities.some(item => item.id === previous)) entity.value = previous;
      else if (entities.some(item => item.id === state.preferredEntity)) entity.value = state.preferredEntity;
      entity.title = entity.selectedOptions[0]?.textContent || '';
      renderEntityMenu(entities);
      fillSystems(entities);
      entity.onchange = () => {
        entity.title = entity.selectedOptions[0]?.textContent || '';
        updateEntityTrigger(entities);
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

  entityTrigger.onclick = () => {
    if (entityTrigger.disabled) return;
    const opening = entityMenu.hidden;
    entityMenu.hidden = !opening;
    entityTrigger.setAttribute('aria-expanded', String(opening));
    if (opening) {
      (entityMenu.querySelector('.selected') || entityMenu.querySelector('[role="option"]'))?.focus();
    }
  };
  entityTrigger.onkeydown = event => {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      entityTrigger.click();
    }
  };
  entityMenu.onkeydown = event => {
    const options = [...entityMenu.querySelectorAll('[role="option"]')];
    const current = options.indexOf(document.activeElement);
    if (event.key === 'Escape') {
      closeEntityMenu();
      entityTrigger.focus();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      options[(current + direction + options.length) % options.length]?.focus();
    }
  };
  document.addEventListener('click', event => {
    if (!event.target.closest('.entity-select')) closeEntityMenu();
  });

  refreshSource();
  setInterval(refreshSource, 1000);
})();
