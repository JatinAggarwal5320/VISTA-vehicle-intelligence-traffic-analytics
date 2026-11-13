import test from 'node:test';
import assert from 'node:assert/strict';
import { trafficReview } from './action.js';

test('chooses the densest five-second window for review', () => {
  const run = { duration: 20, events: [
    { type: 'crossing', time_s: 2 }, { type: 'crossing', time_s: 11 },
    { type: 'crossing', time_s: 12 }, { type: 'stop', time_s: 13 },
  ] };
  const action = trafficReview(run);
  assert.equal(action.start, 10);
  assert.match(action.title, /10–15s/);
  assert.match(action.detail, /low-motion/);
});

test('zero crossing result prompts a line check', () => {
  assert.match(trafficReview({ duration: 10, events: [] }).title, /counting line/);
});
