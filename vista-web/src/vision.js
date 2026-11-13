import * as ort from 'onnxruntime-web/wasm';

const SIZE = 640;
const VEHICLES = new Map([[2, 'car'], [3, 'motorcycle'], [5, 'bus'], [7, 'truck']]);

export function overlap(a, b) {
  const left = Math.max(a.x1, b.x1);
  const top = Math.max(a.y1, b.y1);
  const right = Math.min(a.x2, b.x2);
  const bottom = Math.min(a.y2, b.y2);
  const intersection = Math.max(0, right - left) * Math.max(0, bottom - top);
  const areaA = Math.max(0, a.x2 - a.x1) * Math.max(0, a.y2 - a.y1);
  const areaB = Math.max(0, b.x2 - b.x1) * Math.max(0, b.y2 - b.y1);
  return intersection / Math.max(1, areaA + areaB - intersection);
}

export function nonMaxSuppression(candidates, limit = 50, threshold = 0.45) {
  const chosen = [];
  for (const box of [...candidates].sort((a, b) => b.score - a.score)) {
    if (chosen.every((other) => other.classId !== box.classId || overlap(other, box) < threshold)) {
      chosen.push(box);
      if (chosen.length >= limit) break;
    }
  }
  return chosen;
}

export function parseYoloOutput(data, dims, width, height, scale, padX, padY, minConfidence = 0.25) {
  const anchors = dims[2];
  const candidates = [];
  for (let i = 0; i < anchors; i++) {
    let classId = -1;
    let score = minConfidence;
    for (const id of VEHICLES.keys()) {
      const probability = data[(4 + id) * anchors + i];
      if (probability > score) {
        classId = id;
        score = probability;
      }
    }
    if (classId < 0) continue;
    const cx = data[i];
    const cy = data[anchors + i];
    const w = data[2 * anchors + i];
    const h = data[3 * anchors + i];
    const x1 = Math.max(0, Math.min(width, (cx - w / 2 - padX) / scale));
    const y1 = Math.max(0, Math.min(height, (cy - h / 2 - padY) / scale));
    const x2 = Math.max(0, Math.min(width, (cx + w / 2 - padX) / scale));
    const y2 = Math.max(0, Math.min(height, (cy + h / 2 - padY) / scale));
    if (x2 - x1 < 5 || y2 - y1 < 5) continue;
    candidates.push({ x1, y1, x2, y2, score, classId, label: VEHICLES.get(classId) });
  }
  return nonMaxSuppression(candidates);
}

export async function createDetector(onStatus = () => {}) {
  ort.env.wasm.wasmPaths = '/wasm/';
  ort.env.wasm.numThreads = 1;
  onStatus('Loading YOLOv8n model…');
  const session = await ort.InferenceSession.create('/models/yolov8n.onnx', {
    executionProviders: ['wasm'],
    graphOptimizationLevel: 'all',
  });
  const inputCanvas = document.createElement('canvas');
  inputCanvas.width = SIZE;
  inputCanvas.height = SIZE;
  const context = inputCanvas.getContext('2d', { willReadFrequently: true });
  const floats = new Float32Array(3 * SIZE * SIZE);
  return {
    async detect(source, width, height, confidence) {
      const scale = Math.min(SIZE / width, SIZE / height);
      const scaledWidth = width * scale;
      const scaledHeight = height * scale;
      const padX = (SIZE - scaledWidth) / 2;
      const padY = (SIZE - scaledHeight) / 2;
      context.fillStyle = 'rgb(114,114,114)';
      context.fillRect(0, 0, SIZE, SIZE);
      context.drawImage(source, padX, padY, scaledWidth, scaledHeight);
      const pixels = context.getImageData(0, 0, SIZE, SIZE).data;
      const plane = SIZE * SIZE;
      for (let i = 0; i < plane; i++) {
        const pixel = i * 4;
        floats[i] = pixels[pixel] / 255;
        floats[plane + i] = pixels[pixel + 1] / 255;
        floats[2 * plane + i] = pixels[pixel + 2] / 255;
      }
      const output = await session.run({ images: new ort.Tensor('float32', floats, [1, 3, SIZE, SIZE]) });
      const tensor = output.output0;
      return parseYoloOutput(tensor.data, tensor.dims, width, height, scale, padX, padY, confidence);
    },
    release() { session.release(); },
  };
}
