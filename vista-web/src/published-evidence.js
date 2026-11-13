const STATUS = ['open', 'in_review', 'referred', 'closed'];

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value) node.textContent = value;
  return node;
}

function savedStatus(id) {
  try { return JSON.parse(localStorage.getItem(`vista-action:${id}`)) || {}; }
  catch { return {}; }
}

function cardFor(card) {
  const article = element('article', 'panel evidence-card');
  const meta = element('p', 'step-label', `${card.kind === 'traffic' ? 'TRAFFIC REVIEW' : 'ROAD INSPECTION'} / PYTHON RESULT`);
  const heading = element('h3', '', card.title);
  const place = element('p', 'evidence-place', card.place);
  const media = document.createElement(card.media_type === 'video' ? 'video' : 'img');
  media.className = 'evidence-media'; media.src = card.media_url;
  if (card.media_type === 'video') { media.controls = true; media.preload = 'metadata'; }
  else media.alt = 'Manually marked road defect from the credited public photo';
  const evidence = element('p', 'evidence-detail', card.evidence);
  const next = element('div', 'evidence-next');
  next.append(element('strong', '', 'Next human step'), element('p', '', card.next_step));
  const gate = element('p', 'fine-print', card.gate);
  const source = element('a', 'evidence-source', `Source: ${card.credit} ↗`);
  source.href = card.source_url; source.target = '_blank'; source.rel = 'noopener noreferrer';
  const brief = element('a', 'secondary-button', card.kind === 'traffic' ? 'Open review brief ↗' : 'Open field report ↗');
  brief.href = card.brief_url; brief.target = '_blank'; brief.rel = 'noopener noreferrer';
  const controls = element('div', 'evidence-controls');
  const selection = document.createElement('select'); selection.setAttribute('aria-label', `Review status for ${card.source_id}`);
  for (const status of STATUS) {
    const option = document.createElement('option'); option.value = status;
    option.textContent = status.replace('_', ' '); selection.append(option);
  }
  const note = document.createElement('input'); note.type = 'text'; note.maxLength = 500;
  note.placeholder = 'Your follow-up note'; note.setAttribute('aria-label', `Follow-up note for ${card.source_id}`);
  const save = element('button', 'secondary-button', 'Save on this device'); save.type = 'button';
  const feedback = element('span', 'fine-print', ''); feedback.setAttribute('role', 'status');
  const state = savedStatus(card.id); selection.value = STATUS.includes(state.status) ? state.status : 'open'; note.value = state.note || '';
  save.addEventListener('click', () => {
    if (['referred', 'closed'].includes(selection.value) && !note.value.trim()) {
      feedback.textContent = 'Add a note before marking referred or closed.'; return;
    }
    try {
      localStorage.setItem(`vista-action:${card.id}`, JSON.stringify({ status: selection.value, note: note.value.trim(), updatedAt: new Date().toISOString() }));
      feedback.textContent = 'Saved in this browser only.';
    } catch { feedback.textContent = 'This browser could not save the follow-up.'; }
  });
  controls.append(brief, selection, note, save, feedback);
  article.append(meta, heading, place, media, evidence, next, gate, source, controls);
  return article;
}

export async function renderPublishedEvidence() {
  const container = document.getElementById('publishedEvidence');
  try {
    const response = await fetch('/evidence/index.json');
    if (!response.ok) throw new Error('Evidence bundle is unavailable.');
    const payload = await response.json();
    container.replaceChildren(...payload.cards.map(cardFor));
  } catch (error) {
    container.textContent = error.message;
  }
}
