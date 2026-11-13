import test from 'node:test';
import assert from 'node:assert/strict';
import { nonMaxSuppression, parseYoloOutput } from './vision.js';

test('overlapping vehicles of the same class are suppressed, different classes remain', () => {
  const a = { x1: 0, y1: 0, x2: 20, y2: 20, score: 0.9, classId: 2 };
  const b = { ...a, score: 0.8 };
  const c = { ...a, score: 0.7, classId: 5 };
  assert.deepEqual(nonMaxSuppression([b, c, a]), [a, c]);
});

test('YOLO output restores a padded rectangular frame to source coordinates', () => {
  const anchors = 1;
  const data = new Float32Array(84 * anchors);
  data[0] = 320; data[1] = 320; data[2] = 100; data[3] = 80;
  data[4 + 2] = 0.9;
  const boxes = parseYoloOutput(data, [1, 84, anchors], 640, 320, 1, 0, 160);
  assert.equal(boxes.length, 1);
  assert.deepEqual([boxes[0].x1, boxes[0].y1, boxes[0].x2, boxes[0].y2], [270, 120, 370, 200]);
});
