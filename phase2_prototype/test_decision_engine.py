import json
import tempfile
import unittest
from pathlib import Path

from decision_engine import load_statuses, observation_action, save_status, traffic_action


class DecisionEngineTests(unittest.TestCase):
    def test_traffic_window_is_review_target_not_operational_claim(self):
        summary = {"duration_s": 20, "events": [
            {"type": "crossing", "time_s": 2},
            {"type": "crossing", "time_s": 11},
            {"type": "crossing", "time_s": 12},
            {"type": "stop", "time_s": 13},
        ]}
        action = traffic_action("scene", summary, [])
        self.assertEqual(action["window_start"], 10)
        self.assertIn("10–15s", action["evidence"])
        self.assertIn("manual review", action["next_step"])
        self.assertIn("No signal-timing", action["gate"])

    def test_independent_dated_observation_changes_follow_up(self):
        record = {"id": "OBS-1", "location": "Market Road", "description": "Broken road edge", "camera_lat": 22.5, "camera_lon": 88.3}
        one = observation_action(record, {"recurrence_supported": False})
        repeat = observation_action(record, {"recurrence_supported": True})
        self.assertIn("Locate and verify", one["title"])
        self.assertIn("near source camera", one["next_step"])
        self.assertIn("Refer repeated", repeat["title"])

    def test_status_persists_and_rejects_unknown_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            save_status(folder, "run:abc", "in_review", "Checked 10–15s", "2026-11-13T00:00:00+05:30")
            self.assertEqual(load_statuses(folder)["run:abc"]["note"], "Checked 10–15s")
            with self.assertRaises(ValueError):
                save_status(folder, "run:abc", "made_up", "", "now")
            self.assertEqual(load_statuses(folder)["run:abc"]["status"], "in_review")


if __name__ == "__main__":
    unittest.main()
