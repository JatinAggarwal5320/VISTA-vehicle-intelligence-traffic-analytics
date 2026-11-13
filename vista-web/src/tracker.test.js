import test from 'node:test';
import assert from 'node:assert/strict';
import { VehicleTracker } from './tracker.js';

const detection = (x) => ({ x1: x, y1: 20, x2: x + 20, y2: 40, classId: 2, label: 'car', score: 0.9 });

test('nearby detections retain their IDs when detection order changes', () => {
  const tracker = new VehicleTracker();
  const first = tracker.update([detection(10), detection(70)], 0, 200, 100);
  const second = tracker.update([detection(72), detection(12)], 0.5, 200, 100);
  assert.equal(first[0].id, second.find((track) => track.x1 === 12).id);
  assert.equal(first[1].id, second.find((track) => track.x1 === 72).id);
});

test('a detection after the allowed gap starts a new track', () => {
  const tracker = new VehicleTracker();
  const first = tracker.update([detection(10)], 0, 200, 100)[0];
  const second = tracker.update([detection(10)], 2, 200, 100)[0];
  assert.notEqual(first.id, second.id);
});

test('a short class flicker does not change the tracked vehicle class', () => {
  const tracker = new VehicleTracker();
  tracker.update([detection(10)], 0, 200, 100);
  tracker.update([detection(12)], 0.5, 200, 100);
  const busGuess = { ...detection(14), classId: 5, label: 'bus' };
  const track = tracker.update([busGuess], 1, 200, 100)[0];
  assert.equal(track.label, 'car');
});
