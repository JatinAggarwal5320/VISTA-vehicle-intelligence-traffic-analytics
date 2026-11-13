export class EventEngine {
  constructor(config, width, height) {
    this.config = config;
    this.width = width;
    this.height = height;
    this.line = config.line * (config.axis === 'x' ? width : height);
    this.zone = {
      x1: config.zone[0] * width, y1: config.zone[1] * height,
      x2: config.zone[2] * width, y2: config.zone[3] * height,
    };
    this.states = new Map();
    this.events = [];
    this.samples = [];
    this.lastSampleSecond = -1;
  }

  side(point) {
    const position = this.config.axis === 'x' ? point.x : point.y;
    if (position < this.line - this.config.lineMargin) return -1;
    if (position > this.line + this.config.lineMargin) return 1;
    return 0;
  }

  inside(point) {
    const z = this.zone;
    return point.x >= z.x1 && point.x <= z.x2 && point.y >= z.y1 && point.y <= z.y2;
  }

  update(tracks, time) {
    const newEvents = [];
    for (const box of tracks) {
      const point = { x: (box.x1 + box.x2) / 2, y: box.y2, time };
      let state = this.states.get(box.id);
      if (!state || time - state.last.time > 1.5) {
        state = { last: point, side: null, counted: new Set(), motion: [], since: null, stopReported: false };
        this.states.set(box.id, state);
      }
      const side = this.side(point);
      if (side !== 0) {
        if (state.side === null) state.side = side;
        else if (side !== state.side) {
          const direction = this.config.axis === 'x'
            ? (side > 0 ? 'left_to_right' : 'right_to_left')
            : (side > 0 ? 'top_to_bottom' : 'bottom_to_top');
          if (!state.counted.has(direction)) {
            const event = { type: 'crossing', time_s: time, track_id: box.id,
              vehicle_class: box.label, direction, confidence: Number(box.score.toFixed(3)) };
            this.events.push(event);
            newEvents.push(event);
            state.counted.add(direction);
          }
          state.side = side;
        }
      }
      if (this.inside(point)) {
        state.motion.push(point);
        while (state.motion.length > 1 && time - state.motion[0].time > 1) state.motion.shift();
        const start = state.motion[0];
        const elapsed = time - start.time;
        const speed = elapsed > 0 ? Math.hypot(point.x - start.x, point.y - start.y) / elapsed : Infinity;
        if (elapsed >= 0.8 && speed <= this.config.stationarySpeed) {
          if (state.since === null) state.since = start.time;
          const duration = time - state.since;
          if (duration >= this.config.stopSeconds && !state.stopReported) {
            const event = { type: 'stop', time_s: time, track_id: box.id,
              vehicle_class: box.label, duration_s: Number(duration.toFixed(2)), confidence: Number(box.score.toFixed(3)) };
            this.events.push(event);
            newEvents.push(event);
            state.stopReported = true;
          }
        } else {
          state.since = null;
          state.stopReported = false;
        }
      } else {
        state.motion = [];
        state.since = null;
        state.stopReported = false;
      }
      state.last = point;
    }
    const second = Math.floor(time);
    if (second > this.lastSampleSecond) {
      this.samples.push({ time_s: second, stopped_count: this.stoppedCount(time) });
      this.lastSampleSecond = second;
    }
    return newEvents;
  }

  stoppedCount(time) {
    let count = 0;
    for (const state of this.states.values()) {
      if (state.stopReported && time - state.last.time <= 1.5) count++;
    }
    return count;
  }
}
