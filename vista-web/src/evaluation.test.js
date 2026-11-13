import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateEvents } from './evaluation.js';

test('one prediction cannot satisfy two manual crossing labels', () => {
  const predicted = [{ type: 'crossing', time_s: 10, direction: 'top_to_bottom' }];
  const labelled = [
    { type: 'crossing', time_s: 10.1, direction: 'top_to_bottom' },
    { type: 'crossing', time_s: 10.2, direction: 'top_to_bottom' },
  ];
  const result = evaluateEvents(predicted, labelled, 1);
  assert.deepEqual([result.tp, result.fp, result.fn], [1, 0, 1]);
  assert.equal(result.recall, 0.5);
});

test('wrong direction and distant times do not match', () => {
  const predicted = [{ type: 'crossing', time_s: 10, direction: 'top_to_bottom' }];
  const labelled = [{ type: 'crossing', time_s: 10.1, direction: 'bottom_to_top' }];
  assert.deepEqual([evaluateEvents(predicted, labelled).tp, evaluateEvents(predicted, labelled).fp], [0, 1]);
  assert.equal(evaluateEvents(predicted, [{ ...labelled[0], direction: 'top_to_bottom', time_s: 12 }]).tp, 0);
});
