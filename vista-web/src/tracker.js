import { overlap } from './vision.js';

export class VehicleTracker {
  constructor({ maxGapSeconds = 1.5 } = {}) {
    this.maxGapSeconds = maxGapSeconds;
    this.nextId = 1;
    this.tracks = new Map();
  }

  update(detections, time, width, height) {
    const diagonal = Math.hypot(width, height);
    for (const [id, track] of this.tracks) {
      if (time - track.time > this.maxGapSeconds) this.tracks.delete(id);
    }
    const candidates = [];
    for (const [id, previous] of this.tracks) {
      for (let j = 0; j < detections.length; j++) {
        const current = detections[j];
        const iou = overlap(previous, current);
        const distance = Math.hypot(
          (previous.x1 + previous.x2 - current.x1 - current.x2) / 2,
          (previous.y1 + previous.y2 - current.y1 - current.y2) / 2,
        ) / diagonal;
        const age = time - previous.time;
        const maxDistance = 0.10 + Math.min(0.12, age * 0.04);
        if (iou < 0.08 && distance > maxDistance) continue;
        const classPenalty = previous.classId === current.classId ? 0 : 0.08;
        candidates.push({ id, j, quality: iou * 0.75 + (1 - distance) * 0.25 - classPenalty });
      }
    }
    candidates.sort((a, b) => b.quality - a.quality);
    const assignedTracks = new Set();
    const assignedDetections = new Set();
    const output = [];
    for (const { id, j } of candidates) {
      if (assignedTracks.has(id) || assignedDetections.has(j)) continue;
      assignedTracks.add(id);
      assignedDetections.add(j);
      const current = detections[j];
      const previous = this.tracks.get(id);
      const classVotes = new Map(previous.classVotes);
      const classNames = new Map(previous.classNames);
      classVotes.set(current.classId, (classVotes.get(current.classId) || 0) + 1);
      classNames.set(current.classId, current.label);
      let classId = previous.classId;
      for (const [candidateClass, votes] of classVotes) {
        if (votes > classVotes.get(classId)) classId = candidateClass;
      }
      const item = { ...current, id, time, classVotes, classNames, classId, label: classNames.get(classId) };
      this.tracks.set(id, item);
      output.push(item);
    }
    for (let j = 0; j < detections.length; j++) {
      if (assignedDetections.has(j)) continue;
      const id = this.nextId++;
      const current = detections[j];
      const item = { ...current, id, time,
        classVotes: new Map([[current.classId, 1]]),
        classNames: new Map([[current.classId, current.label]]),
      };
      this.tracks.set(id, item);
      output.push(item);
    }
    return output;
  }
}
