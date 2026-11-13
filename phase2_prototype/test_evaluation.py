import unittest

from evaluation import evaluate_by_type, evaluate_events


class EvaluationTests(unittest.TestCase):
    def test_overlapping_time_windows_keep_two_valid_matches(self):
        predictions = [
            {"type": "crossing", "time_s": 0.4, "direction": "top_to_bottom"},
            {"type": "crossing", "time_s": 0.0, "direction": "top_to_bottom"},
        ]
        labels = [
            {"type": "crossing", "time_s": 0.3, "direction": "top_to_bottom"},
            {"type": "crossing", "time_s": 0.9, "direction": "top_to_bottom"},
        ]
        score = evaluate_events(predictions, labels, tolerance_s=0.6)
        self.assertEqual((score["tp"], score["fp"], score["fn"]), (2, 0, 0))

    def test_one_prediction_cannot_match_two_labels(self):
        predictions = [{"type": "crossing", "time_s": 10, "direction": "top_to_bottom"}]
        labels = [
            {"type": "crossing", "time_s": 10.1, "direction": "top_to_bottom"},
            {"type": "crossing", "time_s": 10.2, "direction": "top_to_bottom"},
        ]
        result = evaluate_events(predictions, labels)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 1))
        self.assertEqual(result["recall"], 0.5)

    def test_wrong_direction_does_not_match(self):
        predictions = [{"type": "crossing", "time_s": 4, "direction": "top_to_bottom"}]
        labels = [{"type": "crossing", "time_s": 4, "direction": "bottom_to_top"}]
        self.assertEqual(evaluate_events(predictions, labels)["tp"], 0)

    def test_stops_are_scored_separately(self):
        predictions = [{"type": "stop", "time_s": 3, "vehicle_class": "car"}]
        labels = [{"type": "stop", "time_s": 3.5}]
        result = evaluate_by_type(predictions, labels)
        self.assertEqual(result["stop"]["tp"], 1)
        self.assertEqual(result["crossing"]["tp"], 0)


if __name__ == "__main__":
    unittest.main()
