import { createDetector } from './vision.js';
import { VehicleTracker } from './tracker.js';
import { EventEngine } from './events.js';
import { deleteRun, getRun, listRuns, saveRun } from './storage.js';
import { summarizeEvaluation } from './evaluation.js';
import { trafficReview } from './action.js';
import { renderPublishedEvidence } from './published-evidence.js';

const $ = (id) => document.getElementById(id);
let selectedFile = null;
let sourceUrl = null;
let resultUrl = null;
let currentRun = null;
let currentRunVideo = null;
let stopRequested = false;
let busy = false;
let zone = [0.05, 0.05, 0.95, 0.90];
let zoneDrag = null;
let toastTimer;

function status(message) { $('statusMessage').textContent = message; }
function toast(message) {
  const element = $('toast');
  element.textContent = message;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 4200);
}
function formatTime(seconds) { return `${Number(seconds).toFixed(1)}s`; }
function displayDirection(direction) { return direction.replaceAll('_', ' '); }

function waitFor(video, eventName, ready) {
  if (ready()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { cleanup(); reject(new Error(`Could not read video (${eventName} timed out).`)); }, 20000);
    const success = () => { cleanup(); resolve(); };
    const failure = () => { cleanup(); reject(new Error('The browser could not decode this video.')); };
    function cleanup() {
      clearTimeout(timeout);
      video.removeEventListener(eventName, success);
      video.removeEventListener('error', failure);
    }
    video.addEventListener(eventName, success, { once: true });
    video.addEventListener('error', failure, { once: true });
  });
}

async function seek(video, time) {
  const target = Math.max(0, Math.min(time, Math.max(0, video.duration - 0.05)));
  if (Math.abs(video.currentTime - target) < 0.015 && video.readyState >= 2) return;
  const completed = waitFor(video, 'seeked', () => false);
  video.currentTime = target;
  await completed;
}

function setupConfig() {
  return {
    axis: $('axis').value,
    line: Number($('line').value) / 100,
    zone: [...zone],
    confidence: Number($('confidence').value) / 100,
    sampleFps: Number($('sampleFps').value),
    stopSeconds: Number($('stopSeconds').value),
    stationarySpeed: Number($('stationarySpeed').value),
    lineMargin: 5,
  };
}

function drawSetup() {
  const video = $('sourceVideo');
  const canvas = $('setupCanvas');
  if (!video.videoWidth || !canvas.width) return;
  const context = canvas.getContext('2d');
  const { width, height } = canvas;
  context.drawImage(video, 0, 0, width, height);
  const z = zoneDrag ? [zoneDrag.x1, zoneDrag.y1, zoneDrag.x2, zoneDrag.y2] : zone;
  const [x1, y1, x2, y2] = z;
  context.fillStyle = 'rgba(16,166,174,.13)';
  context.fillRect(x1 * width, y1 * height, (x2 - x1) * width, (y2 - y1) * height);
  context.strokeStyle = '#31d1da';
  context.lineWidth = Math.max(2, width / 320);
  context.strokeRect(x1 * width, y1 * height, (x2 - x1) * width, (y2 - y1) * height);
  context.strokeStyle = '#f6dc35';
  context.lineWidth = Math.max(3, width / 220);
  context.beginPath();
  if ($('axis').value === 'x') {
    const x = Number($('line').value) / 100 * width;
    context.moveTo(x, 0); context.lineTo(x, height);
  } else {
    const y = Number($('line').value) / 100 * height;
    context.moveTo(0, y); context.lineTo(width, y);
  }
  context.stroke();
}

async function selectVideo(file, isSample = false, isStopDemo = false) {
  if (busy || !file) return;
  if (!file.type.startsWith('video/') && !/\.(mp4|mov|webm|avi)$/i.test(file.name)) {
    toast('Choose an MP4, MOV, WebM or AVI video.'); return;
  }
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  selectedFile = file;
  sourceUrl = URL.createObjectURL(file);
  const video = $('sourceVideo');
  video.src = sourceUrl;
  video.load();
  try {
    await waitFor(video, 'loadedmetadata', () => video.readyState >= 1);
    await waitFor(video, 'loadeddata', () => video.readyState >= 2);
    if (!Number.isFinite(video.duration) || video.duration <= 0) throw new Error('This clip has no readable duration.');
    zone = isSample ? [0.02, 0.05, 0.98, 0.94] : [0.05, 0.05, 0.95, 0.90];
    $('axis').value = 'y';
    $('line').value = isSample ? '55' : '60';
    $('lineValue').textContent = `${$('line').value}%`;
    $('confidence').value = isStopDemo ? '10' : '25';
    $('confidenceValue').textContent = `${$('confidence').value}%`;
    $('setupCanvas').width = video.videoWidth;
    $('setupCanvas').height = video.videoHeight;
    $('frameScrub').max = String(Math.max(0, video.duration - 0.1));
    const previewAt = isSample ? Math.min(6.2, video.duration * 0.4) : Math.min(2, video.duration * 0.2);
    await seek(video, previewAt);
    $('frameScrub').value = String(previewAt);
    $('previewTime').textContent = formatTime(previewAt);
    $('sourceLabel').textContent = file.name;
    $('videoDetails').textContent = `${video.videoWidth} × ${video.videoHeight} · ${formatTime(video.duration)}`;
    $('configuration').hidden = false;
    status('Camera line and stop zone are ready to adjust.');
    drawSetup();
  } catch (error) {
    selectedFile = null;
    $('configuration').hidden = true;
    status(error.message);
    toast(error.message);
  }
}

function setProgress(done, total) {
  const percent = total ? Math.round(done / total * 100) : 0;
  $('progressBar').style.width = `${percent}%`;
  $('progressText').textContent = `${done} / ${total} frames`;
  $('progressPercent').textContent = `${percent}%`;
}

async function analyze() {
  if (!selectedFile || busy) return;
  busy = true;
  stopRequested = false;
  $('startButton').disabled = true;
  $('sampleButton').disabled = true;
  $('stopDemoButton').disabled = true;
  $('progressWrap').hidden = false;
  setProgress(0, 0);
  const started = performance.now();
  const config = setupConfig();
  let detector;
  try {
    detector = await createDetector(status);
    const video = $('analysisVideo');
    video.src = sourceUrl;
    video.load();
    await waitFor(video, 'loadedmetadata', () => video.readyState >= 1);
    await waitFor(video, 'loadeddata', () => video.readyState >= 2);
    const width = video.videoWidth;
    const height = video.videoHeight;
    const duration = video.duration;
    const frameCanvas = document.createElement('canvas');
    frameCanvas.width = width;
    frameCanvas.height = height;
    const context = frameCanvas.getContext('2d');
    const tracker = new VehicleTracker();
    const engine = new EventEngine(config, width, height);
    const records = [];
    const interval = 1 / config.sampleFps;
    const total = Math.max(1, Math.floor((duration - 0.05) / interval) + 1);
    status('Analyzing vehicle frames…');
    for (let index = 0; index < total; index++) {
      if (stopRequested) throw new Error('Analysis stopped.');
      const time = Math.min(index * interval, duration - 0.05);
      await seek(video, time);
      context.drawImage(video, 0, 0, width, height);
      const detections = await detector.detect(frameCanvas, width, height, config.confidence);
      const tracks = tracker.update(detections, time, width, height);
      engine.update(tracks, time);
      records.push({ time_s: Number(time.toFixed(3)), boxes: tracks.map((box) => ({
        id: box.id, label: box.label, score: Number(box.score.toFixed(3)),
        x1: Math.round(box.x1), y1: Math.round(box.y1), x2: Math.round(box.x2), y2: Math.round(box.y2),
      })) });
      setProgress(index + 1, total);
      if (index % 2 === 0) await new Promise(requestAnimationFrame);
    }
    const run = {
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
      sourceName: selectedFile.name,
      width, height, duration: Number(duration.toFixed(2)),
      config, frames: records.length, records,
      events: engine.events, samples: engine.samples,
      labels: [],
      elapsedSeconds: Number(((performance.now() - started) / 1000).toFixed(1)),
      method: 'YOLOv8n ONNX + IoU/center matching',
    };
    try {
      await saveRun(run, selectedFile);
      const crossings = run.events.filter((event) => event.type === 'crossing').length;
      const stops = run.events.filter((event) => event.type === 'stop').length;
      status(`Complete. ${crossings} crossings, ${stops} visible stops recorded; saved on this device.`);
    } catch (error) {
      status('Analysis complete. This browser could not save the run; export the JSON now.');
      toast(`Local storage unavailable: ${error.message}`);
    }
    await showResult(run, selectedFile);
    await renderHistory();
    $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    status(error.message);
    if (!stopRequested) toast(error.message);
  } finally {
    detector?.release();
    busy = false;
    $('startButton').disabled = false;
    $('sampleButton').disabled = false;
    $('stopDemoButton').disabled = false;
    $('progressWrap').hidden = true;
  }
}

function nearestRecord(records, time) {
  if (!records.length) return null;
  let left = 0, right = records.length - 1;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (records[middle].time_s < time) left = middle + 1;
    else right = middle;
  }
  if (left > 0 && Math.abs(records[left - 1].time_s - time) < Math.abs(records[left].time_s - time)) return records[left - 1];
  return records[left];
}

function drawResultOverlay() {
  const canvas = $('resultCanvas');
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (!currentRun || !$('showOverlay').checked) return;
  const { width, height, config } = currentRun;
  const [x1, y1, x2, y2] = config.zone;
  context.fillStyle = 'rgba(15,173,183,.10)';
  context.fillRect(x1 * width, y1 * height, (x2 - x1) * width, (y2 - y1) * height);
  context.strokeStyle = '#3cdae0'; context.lineWidth = 2;
  context.strokeRect(x1 * width, y1 * height, (x2 - x1) * width, (y2 - y1) * height);
  context.strokeStyle = '#f5d739'; context.lineWidth = 3;
  context.beginPath();
  if (config.axis === 'x') {
    const x = config.line * width; context.moveTo(x, 0); context.lineTo(x, height);
  } else {
    const y = config.line * height; context.moveTo(0, y); context.lineTo(width, y);
  }
  context.stroke();
  const record = nearestRecord(currentRun.records, $('resultVideo').currentTime);
  if (!record || Math.abs(record.time_s - $('resultVideo').currentTime) > 1 / config.sampleFps) return;
  context.font = `bold ${Math.max(14, width / 50)}px Arial`;
  for (const box of record.boxes) {
    context.strokeStyle = '#1fe0a0'; context.lineWidth = 2;
    context.strokeRect(box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1);
    const label = `${box.label} #${box.id} ${box.score.toFixed(2)}`;
    const labelWidth = context.measureText(label).width + 10;
    const labelY = Math.max(0, box.y1 - 24);
    context.fillStyle = '#0c3640'; context.fillRect(box.x1, labelY, labelWidth, 22);
    context.fillStyle = '#fff'; context.fillText(label, box.x1 + 5, labelY + 16);
  }
}

function drawTimeline(run) {
  const buckets = Math.max(1, Math.min(12, Math.ceil(run.duration / 5)));
  const counts = Array(buckets).fill(0);
  for (const event of run.events) {
    if (event.type !== 'crossing') continue;
    counts[Math.min(buckets - 1, Math.floor(event.time_s / run.duration * buckets))]++;
  }
  const peak = Math.max(1, ...counts);
  const step = 300 / buckets;
  $('timeline').innerHTML = `<svg viewBox="0 0 320 156" role="img" aria-label="Crossings over video time"><line x1="10" y1="128" x2="310" y2="128" stroke="#cfdee1"/>${counts.map((count, i) => {
    const barHeight = count / peak * 83;
    const x = 10 + i * step + 6;
    return `<rect x="${x}" y="${128 - barHeight}" width="${Math.max(8, step - 12)}" height="${barHeight}" rx="3" fill="#078996"/><text x="${x + Math.max(8, step - 12) / 2}" y="${120 - barHeight}" text-anchor="middle">${count}</text><text x="${x + Math.max(8, step - 12) / 2}" y="148" text-anchor="middle">${Math.round(i * run.duration / buckets)}s</text>`;
  }).join('')}</svg>`;
  const countsByDirection = new Map();
  for (const event of run.events.filter((item) => item.type === 'crossing')) {
    countsByDirection.set(event.direction, (countsByDirection.get(event.direction) || 0) + 1);
  }
  const container = $('directionCounts');
  container.replaceChildren();
  if (!countsByDirection.size) {
    const p = document.createElement('p'); p.className = 'fine-print'; p.textContent = 'No crossings recorded.'; container.append(p);
  }
  for (const [direction, count] of countsByDirection) {
    const row = document.createElement('div');
    const label = document.createElement('span'); label.textContent = displayDirection(direction);
    const value = document.createElement('strong'); value.textContent = String(count);
    row.append(label, value); container.append(row);
  }
}

function renderEvents() {
  if (!currentRun) return;
  const query = $('eventFilter').value.trim().toLowerCase();
  const rows = $('eventRows'); rows.replaceChildren();
  const events = currentRun.events.filter((event) => JSON.stringify(event).toLowerCase().includes(query));
  if (!events.length) {
    const row = document.createElement('tr'); const cell = document.createElement('td');
    cell.colSpan = 5; cell.className = 'empty'; cell.textContent = query ? 'No matching events.' : 'No crossing or visible stop events in this run.';
    row.append(cell); rows.append(row); return;
  }
  for (const event of events) {
    const row = document.createElement('tr');
    const timeCell = document.createElement('td');
    const jump = document.createElement('button'); jump.textContent = formatTime(event.time_s);
    jump.addEventListener('click', () => { $('resultVideo').currentTime = Math.max(0, event.time_s - 0.5); $('resultVideo').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
    timeCell.append(jump);
    const type = document.createElement('td'); const badge = document.createElement('span'); badge.className = `tag ${event.type}`; badge.textContent = event.type; type.append(badge);
    const vehicle = document.createElement('td'); vehicle.textContent = event.vehicle_class;
    const track = document.createElement('td'); track.textContent = `#${event.track_id}`;
    const detail = document.createElement('td'); detail.textContent = event.type === 'crossing' ? displayDirection(event.direction) : `${event.duration_s.toFixed(1)}s visibly stopped`;
    row.append(timeCell, type, vehicle, track, detail); rows.append(row);
  }
}

function renderLabels() {
  if (!currentRun) return;
  const container = $('manualLabels'); container.replaceChildren();
  const labels = currentRun.labels || [];
  for (const [index, label] of labels.entries()) {
    const row = document.createElement('div'); row.className = 'manual-label';
    const text = document.createElement('span'); text.textContent = `${formatTime(label.time_s)} · ${label.type}${label.direction ? ` · ${displayDirection(label.direction)}` : ''}`;
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
    remove.addEventListener('click', async () => { labels.splice(index, 1); await persistLabels(); renderLabels(); });
    row.append(text, remove); container.append(row);
  }
  const metrics = $('metrics'); metrics.replaceChildren();
  if (!labels.length) {
    const p = document.createElement('p'); p.className = 'fine-print'; p.textContent = 'Add manual labels to calculate precision and recall.'; metrics.append(p); return;
  }
  const summary = summarizeEvaluation(currentRun.events, labels, 1);
  for (const kind of ['crossing', 'stop']) {
    const count = labels.filter((label) => label.type === kind).length;
    if (!count) continue;
    const result = summary[kind];
    const row = document.createElement('div');
    const title = document.createElement('strong'); title.textContent = `${kind === 'crossing' ? 'Crossings' : 'Stops'} · ±1s`;
    const values = document.createElement('span'); values.textContent = `P ${(result.precision * 100).toFixed(0)}% · R ${(result.recall * 100).toFixed(0)}%`;
    row.append(title, values); metrics.append(row);
    const counts = document.createElement('p'); counts.className = 'fine-print'; counts.textContent = `${result.tp} matched · ${result.fp} extra · ${result.fn} missed`;
    metrics.append(counts);
  }
  const note = document.createElement('p'); note.className = 'fine-print'; note.textContent = 'These metrics are meaningful only after you label the entire clip.'; metrics.append(note);
}

async function persistLabels() {
  try { await saveRun(currentRun, currentRunVideo); }
  catch (error) { toast(`Could not save manual labels: ${error.message}`); }
}

async function showResult(run, video) {
  currentRun = run;
  currentRunVideo = video;
  if (resultUrl) URL.revokeObjectURL(resultUrl);
  resultUrl = URL.createObjectURL(video);
  const resultVideo = $('resultVideo');
  resultVideo.src = resultUrl;
  resultVideo.load();
  $('resultCanvas').width = run.width;
  $('resultCanvas').height = run.height;
  $('resultMeta').textContent = `${run.sourceName} · ${formatTime(run.duration)} · ${run.width} × ${run.height} · ${run.method}`;
  $('crossingCount').textContent = String(run.events.filter((event) => event.type === 'crossing').length);
  $('stopCount').textContent = String(run.events.filter((event) => event.type === 'stop').length);
  $('frameCount').textContent = String(run.frames);
  $('elapsedCount').textContent = formatTime(run.elapsedSeconds);
  const review = trafficReview(run);
  $('liveActionTitle').textContent = review.title;
  $('liveActionDetail').textContent = review.detail;
  $('liveActionJump').onclick = () => {
    $('resultVideo').currentTime = review.start;
    $('resultVideo').scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  $('results').hidden = false;
  $('eventFilter').value = '';
  $('showOverlay').checked = true;
  $('manualDirection').replaceChildren();
  const choices = run.config.axis === 'x' ? ['left_to_right', 'right_to_left'] : ['top_to_bottom', 'bottom_to_top'];
  for (const direction of choices) {
    const option = document.createElement('option'); option.value = direction; option.textContent = displayDirection(direction); $('manualDirection').append(option);
  }
  $('manualType').value = 'crossing'; $('manualDirectionWrap').hidden = false;
  drawTimeline(run); renderEvents(); renderLabels();
  try {
    await waitFor(resultVideo, 'loadedmetadata', () => resultVideo.readyState >= 1);
    await seek(resultVideo, Math.min(6.2, run.duration * 0.4));
  } catch {
    // The event table and exports still work if a saved video cannot be decoded.
  }
  drawResultOverlay();
}

async function renderHistory() {
  const container = $('runHistory'); container.replaceChildren();
  let runs;
  try { runs = await listRuns(); }
  catch (error) { const p = document.createElement('p'); p.className = 'fine-print'; p.textContent = `Local run history unavailable: ${error.message}`; container.append(p); return; }
  if (!runs.length) { const p = document.createElement('p'); p.className = 'fine-print'; p.textContent = 'No saved runs yet.'; container.append(p); return; }
  for (const run of runs.slice(0, 12)) {
    const row = document.createElement('div'); row.className = 'history-item';
    const open = document.createElement('button'); open.className = 'open-run'; open.type = 'button';
    const title = document.createElement('strong'); title.textContent = run.sourceName;
    const meta = document.createElement('small'); meta.textContent = `${new Date(run.createdAt).toLocaleDateString()} · ${run.events.length} events`;
    open.append(title, meta);
    open.addEventListener('click', async () => {
      const saved = await getRun(run.id);
      if (!saved) { toast('Saved video was not found.'); return; }
      await showResult(saved.run, saved.video);
      $('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    const remove = document.createElement('button'); remove.className = 'delete-run'; remove.type = 'button'; remove.title = 'Delete saved run'; remove.textContent = '×';
    remove.addEventListener('click', async () => { await deleteRun(run.id); if (currentRun?.id === run.id) { currentRun = null; $('results').hidden = true; } await renderHistory(); });
    row.append(open, remove); container.append(row);
  }
}

function downloadBlob(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function csvCell(value) { return `"${String(value ?? '').replaceAll('"', '""')}"`; }
function eventsCsv(events) {
  const fields = ['type', 'time_s', 'track_id', 'vehicle_class', 'direction', 'duration_s', 'confidence'];
  return [fields.join(','), ...events.map((event) => fields.map((field) => csvCell(event[field])).join(','))].join('\n');
}

$('fileInput').addEventListener('change', (event) => selectVideo(event.target.files?.[0]));
async function loadSample(path, name, isStopDemo = false) {
  try {
    status('Loading included sample…');
    const response = await fetch(path);
    if (!response.ok) throw new Error('The sample video could not be loaded.');
    const blob = await response.blob();
    await selectVideo(new File([blob], name, { type: 'video/mp4' }), true, isStopDemo);
  } catch (error) { status(error.message); toast(error.message); }
}
$('sampleButton').addEventListener('click', () => loadSample('/sample/traffic.mp4', 'Intel traffic sample.mp4'));
$('stopDemoButton').addEventListener('click', () => loadSample('/sample/stopped-demo.mp4', 'Synthetic stop demo.mp4', true));
$('axis').addEventListener('change', drawSetup);
$('line').addEventListener('input', () => { $('lineValue').textContent = `${$('line').value}%`; drawSetup(); });
$('confidence').addEventListener('input', () => { $('confidenceValue').textContent = `${$('confidence').value}%`; });
$('frameScrub').addEventListener('change', async () => { try { await seek($('sourceVideo'), Number($('frameScrub').value)); $('previewTime').textContent = formatTime($('sourceVideo').currentTime); drawSetup(); } catch (error) { toast(error.message); } });
$('resetZone').addEventListener('click', () => { zone = [0.05, 0.05, 0.95, 0.90]; drawSetup(); });
$('setupCanvas').addEventListener('pointerdown', (event) => {
  const box = event.currentTarget.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
  const y = Math.max(0, Math.min(1, (event.clientY - box.top) / box.height));
  zoneDrag = { x1: x, y1: y, x2: x, y2: y, fromX: x, fromY: y };
  event.currentTarget.setPointerCapture(event.pointerId);
});
$('setupCanvas').addEventListener('pointermove', (event) => {
  if (!zoneDrag) return;
  const box = event.currentTarget.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
  const y = Math.max(0, Math.min(1, (event.clientY - box.top) / box.height));
  zoneDrag.x1 = Math.min(zoneDrag.fromX, x); zoneDrag.y1 = Math.min(zoneDrag.fromY, y);
  zoneDrag.x2 = Math.max(zoneDrag.fromX, x); zoneDrag.y2 = Math.max(zoneDrag.fromY, y);
  drawSetup();
});
$('setupCanvas').addEventListener('pointerup', () => {
  if (!zoneDrag) return;
  if (zoneDrag.x2 - zoneDrag.x1 > 0.03 && zoneDrag.y2 - zoneDrag.y1 > 0.03) zone = [zoneDrag.x1, zoneDrag.y1, zoneDrag.x2, zoneDrag.y2];
  zoneDrag = null; drawSetup();
});
$('startButton').addEventListener('click', analyze);
$('cancelButton').addEventListener('click', () => { stopRequested = true; status('Stopping after the current frame…'); });
$('resultVideo').addEventListener('timeupdate', drawResultOverlay);
$('resultVideo').addEventListener('seeked', drawResultOverlay);
$('resultVideo').addEventListener('loadeddata', drawResultOverlay);
$('showOverlay').addEventListener('change', drawResultOverlay);
$('eventFilter').addEventListener('input', renderEvents);
$('manualType').addEventListener('change', () => { $('manualDirectionWrap').hidden = $('manualType').value !== 'crossing'; });
$('addLabel').addEventListener('click', async () => {
  if (!currentRun) return;
  const type = $('manualType').value;
  const label = { type, time_s: Number($('resultVideo').currentTime.toFixed(2)) };
  if (type === 'crossing') label.direction = $('manualDirection').value;
  currentRun.labels ||= [];
  currentRun.labels.push(label);
  currentRun.labels.sort((a, b) => a.time_s - b.time_s);
  await persistLabels(); renderLabels();
});
$('exportCsv').addEventListener('click', () => currentRun && downloadBlob('vista-events.csv', eventsCsv(currentRun.events), 'text/csv'));
$('exportJson').addEventListener('click', () => currentRun && downloadBlob('vista-run.json', JSON.stringify(currentRun, null, 2), 'application/json'));
$('exportLabels').addEventListener('click', () => currentRun && downloadBlob('vista-manual-labels.csv', eventsCsv(currentRun.labels || []), 'text/csv'));

renderHistory();
renderPublishedEvidence();
