"""Run a small deterministic demonstration of the VISTA event rules."""

import json

from vista_events import EventEngine, TrackPoint, Zone


engine = EventEngine(line_x=50, stop_zone=Zone(0, 0, 40, 100))
tracks = {
    1: [10, 25, 40, 60, 75],  # crosses left to right
    2: [20, 20, 20, 20, 20],  # remains stopped in the visible zone
    3: [47, 51, 49, 53, 48],  # near-line jitter, no crossing
}

for second in range(5):
    for track_id, xs in tracks.items():
        engine.update(TrackPoint(second, track_id, xs[second], 50, "car"))

print(json.dumps({**engine.result(), "stopped_count_at_4s": engine.stopped_count(4)}, indent=2))
