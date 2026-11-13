function compatible(prediction, label, tolerance) {
  if (prediction.type !== label.type) return false;
  if (Math.abs(prediction.time_s - label.time_s) > tolerance) return false;
  if (label.type === 'crossing' && prediction.direction !== label.direction) return false;
  if (label.vehicle_class && prediction.vehicle_class !== label.vehicle_class) return false;
  return true;
}

export function evaluateEvents(predictions, labels, tolerance = 1) {
  const pairs = [];
  for (let p = 0; p < predictions.length; p++) {
    for (let l = 0; l < labels.length; l++) {
      if (compatible(predictions[p], labels[l], tolerance)) {
        pairs.push({ p, l, distance: Math.abs(predictions[p].time_s - labels[l].time_s) });
      }
    }
  }
  pairs.sort((a, b) => a.distance - b.distance);
  const usedPredictions = new Set();
  const usedLabels = new Set();
  const matches = [];
  for (const pair of pairs) {
    if (usedPredictions.has(pair.p) || usedLabels.has(pair.l)) continue;
    usedPredictions.add(pair.p);
    usedLabels.add(pair.l);
    matches.push(pair);
  }
  const tp = matches.length;
  const fp = predictions.length - tp;
  const fn = labels.length - tp;
  const precision = tp + fp ? tp / (tp + fp) : 0;
  const recall = tp + fn ? tp / (tp + fn) : 0;
  const f1 = precision + recall ? 2 * precision * recall / (precision + recall) : 0;
  return { tp, fp, fn, precision, recall, f1, matches };
}

export function summarizeEvaluation(predictions, labels, tolerance = 1) {
  return Object.fromEntries(['crossing', 'stop'].map((type) => [
    type,
    evaluateEvents(
      predictions.filter((item) => item.type === type),
      labels.filter((item) => item.type === type),
      tolerance,
    ),
  ]));
}
