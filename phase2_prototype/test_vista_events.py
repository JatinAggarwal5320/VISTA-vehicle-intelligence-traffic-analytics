import unittest

from vista_events import EventEngine, TrackPoint, Zone


def point(t, track_id, x, y=50):
    return TrackPoint(time_s=t, track_id=track_id, x=x, y=y, vehicle_class="car")


class EventEngineTests(unittest.TestCase):
    def make_engine(self):
        return EventEngine(line_x=50, stop_zone=Zone(0, 0, 40, 100))

    def test_one_left_to_right_crossing_for_one_track(self):
        engine = self.make_engine()
        for item in [point(0, 1, 10), point(1, 1, 40), point(2, 1, 60), point(3, 1, 75)]:
            engine.update(item)
        self.assertEqual([(e.track_id, e.direction) for e in engine.crossings], [(1, "left_to_right")])

    def test_jitter_inside_margin_does_not_cross(self):
        engine = self.make_engine()
        for i, x in enumerate([47, 51, 49, 53, 48]):
            engine.update(point(i, 2, x))
        self.assertEqual(engine.crossings, [])

    def test_reverse_direction_is_recorded(self):
        engine = self.make_engine()
        for i, x in enumerate([90, 70, 55, 40, 20]):
            engine.update(point(i, 3, x))
        self.assertEqual([e.direction for e in engine.crossings], ["right_to_left"])

    def test_horizontal_line_records_top_to_bottom(self):
        engine = EventEngine(line_x=None, line_y=50, stop_zone=Zone(0, 0, 100, 40))
        for i, y in enumerate([20, 40, 50, 60, 80]):
            engine.update(point(i, 7, 50, y))
        self.assertEqual([e.direction for e in engine.crossings], ["top_to_bottom"])

    def test_requires_one_line_orientation(self):
        with self.assertRaises(ValueError):
            EventEngine(line_x=None, stop_zone=Zone(0, 0, 100, 100))
        with self.assertRaises(ValueError):
            EventEngine(line_x=10, line_y=20, stop_zone=Zone(0, 0, 100, 100))

    def test_stationary_track_generates_one_stop_event(self):
        engine = self.make_engine()
        for t in range(4):
            engine.update(point(t, 4, 20))
        self.assertEqual(len(engine.stops), 1)
        self.assertEqual(engine.stops[0].duration_s, 2)
        self.assertEqual(engine.stopped_count(3), 1)

    def test_stationary_box_jitter_at_video_rate_still_counts_as_stop(self):
        engine = self.make_engine()
        for frame in range(39):
            x = 20 + (frame % 3 - 1) * 2
            engine.update(point(frame / 12.5, 8, x))
        self.assertEqual(len(engine.stops), 1)

    def test_long_tracking_gap_does_not_create_crossing(self):
        engine = self.make_engine()
        engine.update(point(0, 9, 10))
        engine.update(point(3, 9, 90))
        self.assertEqual(engine.crossings, [])

    def test_moving_track_is_not_marked_stopped(self):
        engine = self.make_engine()
        for i, x in enumerate([5, 12, 19, 26, 33]):
            engine.update(point(i, 5, x))
        self.assertEqual(engine.stops, [])
        self.assertEqual(engine.stopped_count(4), 0)

    def test_stale_track_is_not_in_current_stopped_count(self):
        engine = self.make_engine()
        for t in range(3):
            engine.update(point(t, 6, 20))
        self.assertEqual(engine.stopped_count(2), 1)
        self.assertEqual(engine.stopped_count(5), 0)


if __name__ == "__main__":
    unittest.main()
