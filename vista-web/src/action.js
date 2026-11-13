export function trafficReview(run) {
  const crossings = run.events.filter((event) => event.type === 'crossing');
  const stops = run.events.filter((event) => event.type === 'stop');
  const bins = new Map();
  for (const event of crossings) {
    const start = Math.floor(event.time_s / 5) * 5;
    bins.set(start, (bins.get(start) || 0) + 1);
  }
  const busiest = [...bins].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0];
  if (!busiest) return {
    title: 'Check the counting line', start: 0,
    detail: 'No crossing candidates were recorded. Watch the clip to see whether vehicles cross the chosen line, then adjust it if needed.',
  };
  const [start, count] = busiest;
  const end = Math.min(start + 5, run.duration);
  const stopNote = stops.length ? ` ${stops.length} low-motion stop candidates also need manual review.` : '';
  return {
    title: `Verify ${start}–${end}s of footage`, start,
    detail: `${count} model crossing candidate${count === 1 ? '' : 's'} in this window. Check track IDs against the original video and label the full clip before trusting the count.${stopNote}`,
  };
}
