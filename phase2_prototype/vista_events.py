"""Camera-coordinate event rules for the VISTA Phase 2 prototype.

Input is a stream of tracked vehicle points. A detector/tracker is deliberately
outside this module so the line and waiting rules can be tested independently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import hypot
from typing import Literal


Direction = Literal["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"]


@dataclass(frozen=True)
class TrackPoint:
    time_s: float
    track_id: int
    x: float
    y: float
    vehicle_class: str = "vehicle"


@dataclass(frozen=True)
class Zone:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def contains(self, point: TrackPoint) -> bool:
        return self.x_min <= point.x <= self.x_max and self.y_min <= point.y <= self.y_max


@dataclass(frozen=True)
class CrossingEvent:
    time_s: float
    track_id: int
    direction: Direction
    vehicle_class: str


@dataclass(frozen=True)
class StopEvent:
    time_s: float
    track_id: int
    duration_s: float
    vehicle_class: str


@dataclass
class _TrackState:
    last: TrackPoint | None = None
    stable_side: int | None = None
    counted_directions: set[Direction] = field(default_factory=set)
    stationary_since: float | None = None
    stop_reported: bool = False
    motion_history: list[TrackPoint] = field(default_factory=list)


class EventEngine:
    """Record one crossing per track/direction and visible stops in a zone.

    All distances are image pixels. The stop result is a visible waiting proxy,
    not physical speed, total queue length, or the cause of a stop.
    """

    def __init__(
        self,
        line_x: float | None,
        stop_zone: Zone,
        *,
        line_y: float | None = None,
        line_margin_px: float = 5.0,
        max_stationary_speed_px_s: float = 2.0,
        min_stop_s: float = 2.0,
        active_track_age_s: float = 1.5,
        motion_window_s: float = 1.0,
        max_track_gap_s: float = 1.5,
    ) -> None:
        if line_margin_px < 0 or max_stationary_speed_px_s < 0 or min_stop_s <= 0 or motion_window_s <= 0 or max_track_gap_s <= 0:
            raise ValueError("Margins and speed must be nonnegative; times must be positive")
        if (line_x is None) == (line_y is None):
            raise ValueError("Set exactly one of line_x or line_y")
        self.line_x = line_x
        self.line_y = line_y
        self.stop_zone = stop_zone
        self.line_margin_px = line_margin_px
        self.max_stationary_speed_px_s = max_stationary_speed_px_s
        self.min_stop_s = min_stop_s
        self.active_track_age_s = active_track_age_s
        self.motion_window_s = motion_window_s
        self.max_track_gap_s = max_track_gap_s
        self._tracks: dict[int, _TrackState] = {}
        self.crossings: list[CrossingEvent] = []
        self.stops: list[StopEvent] = []

    def _side(self, point: TrackPoint) -> int:
        position = point.x if self.line_x is not None else point.y
        line = self.line_x if self.line_x is not None else self.line_y
        assert line is not None
        if position < line - self.line_margin_px:
            return -1
        if position > line + self.line_margin_px:
            return 1
        return 0

    def update(self, point: TrackPoint) -> list[CrossingEvent | StopEvent]:
        state = self._tracks.setdefault(point.track_id, _TrackState())
        previous = state.last
        if previous is not None and point.time_s <= previous.time_s:
            raise ValueError("Timestamps must increase for each track")
        if previous is not None and point.time_s - previous.time_s > self.max_track_gap_s:
            state = self._tracks[point.track_id] = _TrackState()
            previous = None

        emitted: list[CrossingEvent | StopEvent] = []
        side = self._side(point)
        if side != 0:
            if state.stable_side is None:
                state.stable_side = side
            elif side != state.stable_side:
                if self.line_x is not None:
                    direction: Direction = "left_to_right" if side == 1 else "right_to_left"
                else:
                    direction = "top_to_bottom" if side == 1 else "bottom_to_top"
                if direction not in state.counted_directions:
                    event = CrossingEvent(point.time_s, point.track_id, direction, point.vehicle_class)
                    self.crossings.append(event)
                    emitted.append(event)
                    state.counted_directions.add(direction)
                state.stable_side = side

        if self.stop_zone.contains(point):
            state.motion_history.append(point)
            while len(state.motion_history) > 1 and point.time_s - state.motion_history[0].time_s > self.motion_window_s:
                state.motion_history.pop(0)
            start = state.motion_history[0]
            elapsed = point.time_s - start.time_s
            if elapsed >= self.motion_window_s * 0.8 and hypot(point.x - start.x, point.y - start.y) / elapsed <= self.max_stationary_speed_px_s:
                if state.stationary_since is None:
                    state.stationary_since = start.time_s
                duration = point.time_s - state.stationary_since
                if duration >= self.min_stop_s and not state.stop_reported:
                    event = StopEvent(point.time_s, point.track_id, duration, point.vehicle_class)
                    self.stops.append(event)
                    emitted.append(event)
                    state.stop_reported = True
            else:
                state.stationary_since = None
                state.stop_reported = False
        else:
            state.motion_history.clear()
            state.stationary_since = None
            state.stop_reported = False

        state.last = point
        return emitted

    def stopped_count(self, time_s: float) -> int:
        """Number of recently observed tracks that currently satisfy the stop rule."""
        return sum(
            state.stop_reported
            and state.last is not None
            and 0 <= time_s - state.last.time_s <= self.active_track_age_s
            for state in self._tracks.values()
        )

    def result(self) -> dict:
        return {
            "crossings": [asdict(event) for event in self.crossings],
            "stops": [asdict(event) for event in self.stops],
        }
