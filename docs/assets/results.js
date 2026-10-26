(() => {
  const controls = document.querySelector('.result-switch');
  const overall = document.getElementById('overall-view');
  const quality = document.getElementById('quality-view');
  if (controls && overall && quality) {
    controls.hidden = false;
    controls.addEventListener('click', (event) => {
      const button = event.target.closest('[data-results-view]');
      if (!button) return;
      const showQuality = button.dataset.resultsView === 'quality';
      overall.hidden = showQuality;
      quality.hidden = !showQuality;
      controls.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      document.querySelector('.ranking-note').textContent = showQuality
        ? 'Models stay in Overall score order. Answer quality covers only the tasks each model answered.'
        : 'Muse Wonder takes first place on Overall score.';
    });
  }

  const variant = document.getElementById('variant-filter');
  if (variant) {
    variant.closest('label').hidden = false;
    variant.addEventListener('change', () => {
      let count = 0;
      document.querySelectorAll('.artifact-table tbody tr').forEach(row => {
        row.hidden = variant.value !== 'all' && row.dataset.variant !== variant.value;
        if (!row.hidden) count++;
      });
      document.getElementById('artifact-count').textContent = count + ' binaries';
    });
  }

  const copy = document.getElementById('copy-citation');
  if (copy) {
    copy.hidden = false;
    copy.addEventListener('click', async () => {
      const status = document.getElementById('citation-status');
      try {
        await navigator.clipboard.writeText(document.getElementById('citation-text').textContent.trim());
        status.textContent = 'Citation copied.';
      } catch {
        status.textContent = 'Select the citation text above to copy it.';
      }
    });
  }

  function revealAnchor(hash) {
    let target;
    try { target = document.getElementById(decodeURIComponent(hash.slice(1))); } catch { return; }
    while (target) {
      if (target.tagName === 'DETAILS') target.open = true;
      target = target.parentElement;
    }
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link) revealAnchor(link.hash);
  });
  window.addEventListener('hashchange', () => revealAnchor(location.hash));
  revealAnchor(location.hash);

  const source = document.getElementById('results-data');
  if (!source) return;
  let data;
  try { data = JSON.parse(source.textContent); } catch { return; }
  const byId = new Map(data.models.map(model => [model.id, model]));
  const leftInput = document.getElementById('compare-left');
  const rightInput = document.getElementById('compare-right');
  const fields = [['techniques', 'Techniques'], ['injection_details', 'Injection details'],
    ['encryption_algorithm', 'Algorithms'], ['encryption_key', 'Keys'], ['anti_analysis', 'Anti-analysis']];
  const sign = n => (n >= 0 ? '+' : '−') + Math.abs(n).toFixed(4);
  let previousLeft = leftInput.value;
  let previousRight = rightInput.value;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function renderRows(target, left, right, fieldView) {
    const body = document.createDocumentFragment();
    const metrics = fieldView ? fields : [['overall', 'Overall'], ['main', 'Main'], ['bonus', 'Bonus']];
    for (const [key, label] of metrics) {
      const row = element('tr');
      const heading = element('th', label);
      heading.scope = 'row';
      row.append(heading);
      for (const model of [left, right]) {
        const value = fieldView ? model.fields[key].mean_score : model[key];
        const note = fieldView ? model.fields[key].answers + ' valid answers'
          : ({overall: 100, main: 90, bonus: 10}[key]) + ' attempts';
        const cell = element('td');
        cell.append(element('span', value.toFixed(2), 'compare-value'), element('span', note, 'model-meta'));
        const track = element('span', undefined, 'compare-track');
        track.setAttribute('aria-hidden', 'true');
        const fill = element('span');
        fill.style.width = value.toFixed(4) + '%';
        track.append(fill);
        cell.append(track);
        row.append(cell);
      }
      body.append(row);
    }
    if (fieldView) {
      const row = element('tr');
      const heading = element('th', 'Correct key bytes');
      heading.scope = 'row';
      row.append(heading);
      for (const model of [left, right]) {
        const cell = element('td');
        cell.append(element('span', model.key_bytes.correct + '/' + model.key_bytes.total, 'compare-value'),
          element('span', 'required components', 'model-meta'));
        row.append(cell);
      }
      body.append(row);
    }
    target.replaceChildren(body);
  }

  function update(changed) {
    if (leftInput.value === rightInput.value) {
      if (changed === 'left') rightInput.value = previousLeft;
      else leftInput.value = previousRight;
    }
    const left = byId.get(leftInput.value), right = byId.get(rightInput.value);
    if (!left || !right || left === right) return;
    previousLeft = left.id;
    previousRight = right.id;
    for (const option of leftInput.options) option.disabled = option.value === right.id;
    for (const option of rightInput.options) option.disabled = option.value === left.id;
    for (const [side, model] of [['left', left], ['right', right]]) {
      document.querySelectorAll('[data-compare-name="' + side + '"]').forEach(node => { node.textContent = model.name; });
      document.getElementById('compare-' + side + '-meta').textContent = model.name + ' · ' + model.reasoning
        + ' thinking · ' + model.refusals + ' refusals/blocks · ' + model.budget + ' budget exits';
    }
    document.getElementById('compare-coverage').textContent = left.name + ': ' + left.valid + '/100 valid answers. '
      + right.name + ': ' + right.valid + '/100. Overall includes all 100 attempts for each model.';
    document.getElementById('compare-subsets').textContent = (left.valid === 100 && right.valid === 100
      ? 'Both models answered every attempt. '
      : 'These models answered different subsets; field differences are descriptive, not a controlled comparison. ')
      + 'Field scores average valid answers where the field applies. Each count is shown below.';
    renderRows(document.querySelector('#compare-scores tbody'), left, right, false);
    renderRows(document.querySelector('#compare-fields tbody'), left, right, true);
    const pair = data.pairs.find(p => (p.left === left.id && p.right === right.id) || (p.right === left.id && p.left === right.id));
    if (pair) {
      const interval = pair.left === left.id ? pair.interval : [-pair.interval[1], -pair.interval[0]];
      const difference = pair.left === left.id ? pair.difference : -pair.difference;
      document.getElementById('compare-interval').textContent = left.name + ' minus ' + right.name + ': '
        + sign(difference) + ' points. Simultaneous 95% interval: ' + sign(interval[0]) + ' to ' + sign(interval[1]) + '.';
      document.getElementById('compare-interpretation').textContent = interval[0] <= 0 && interval[1] >= 0
        ? 'The interval includes zero; these runs do not establish which model would score higher on repeat.'
        : 'The interval favors ' + (interval[0] > 0 ? left.name : right.name) + ' for repeated runs on this fixed suite.';
    }
  }
  leftInput.addEventListener('change', () => update('left'));
  rightInput.addEventListener('change', () => update('right'));
  document.getElementById('compare-swap').addEventListener('click', () => {
    const left = leftInput.value;
    leftInput.value = rightInput.value;
    rightInput.value = left;
    update('swap');
  });
  update('initial');
  document.querySelector('.compare-controls').hidden = false;
})();
