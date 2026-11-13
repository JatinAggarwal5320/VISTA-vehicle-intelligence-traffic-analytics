import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEngine } from './events.js';

const settings = {
  axis: 'y', line: 0.5, zone: [0.1, 0.1, 0.9, 0.9],
  lineMargin: 3, stopSeconds: 2, stationarySpeed: 8,
};
const box = (id, x, bottom) => ({ id, x1: x - 10, x2: x + 10, y1: bottom - 20, y2: bottom, label: 'car', score: 0.9 });

test('a continuous track crossing the line creates one directional event', () => {
  const engine = new EventEngine(settings, 100, 100);
  engine.update([box(7, 50, 30)], 0);
  engine.update([box(7, 50, 49)], 0.5);
  engine.update([box(7, 50, 70)], 1);
  engine.update([box(7, 50, 75)], 1.5);
  assert.equal(engine.events.length, 1);
  assert.deepEqual([engine.events[0].type, engine.events[0].direction, engine.events[0].track_id], ['crossing', 'top_to_bottom', 7]);
});

test('a stationary vehicle is reported only after the stop duration', () => {
  const engine = new EventEngine(settings, 100, 100);
  for (let t = 0; t <= 4; t += 0.5) engine.update([box(3, 50, 70)], t);
  const stops = engine.events.filter((event) => event.type === 'stop');
  assert.equal(stops.length, 1);
  assert.ok(stops[0].time_s >= 2);
  assert.equal(stops[0].track_id, 3);
});

test('track disappearance cannot create a crossing event', () => {
  const engine = new EventEngine(settings, 100, 100);
  engine.update([box(5, 50, 30)], 0);
  engine.update([], 0.5);
  engine.update([box(5, 50, 70)], 2);
  assert.equal(engine.events.filter((event) => event.type === 'crossing').length, 0);
});
