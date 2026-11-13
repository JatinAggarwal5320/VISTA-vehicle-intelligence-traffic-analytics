"""Compare VISTA events with manually reviewed event timestamps."""

from __future__ import annotations

from typing import Any


def evaluate_events(
    predictions: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    *,
    tolerance_s: float = 1.0,
) -> dict[str, float | int]:
    """Match events one to one by type, direction and timestamp.

    A label may include ``vehicle_class``; an empty value leaves class out of
    the comparison. Matching maximizes the number of valid one-to-one pairs,
    preferring nearby timestamps when several assignments are possible.
    """
    if tolerance_s < 0:
        raise ValueError("tolerance_s must be nonnegative")
    candidates: dict[int, list[tuple[float, int]]] = {index: [] for index in range(len(predictions))}
    for prediction_index, prediction in enumerate(predictions):
        for label_index, label in enumerate(labels):
            if prediction.get("type") != label.get("type"):
                continue
            if prediction.get("type") == "crossing" and prediction.get("direction") != label.get("direction"):
                continue
            if label.get("vehicle_class") and prediction.get("vehicle_class") != label.get("vehicle_class"):
                continue
            gap = abs(float(prediction["time_s"]) - float(label["time_s"]))
            if gap <= tolerance_s:
                candidates[prediction_index].append((gap, label_index))
    for options in candidates.values():
        options.sort()
    assigned_label: dict[int, int] = {}

    def assign(prediction_index: int, visited: set[int]) -> bool:
        for _, label_index in candidates[prediction_index]:
            if label_index in visited:
                continue
            visited.add(label_index)
            previous = assigned_label.get(label_index)
            if previous is None or assign(previous, visited):
                assigned_label[label_index] = prediction_index
                return True
        return False

    for prediction_index in sorted(candidates, key=lambda index: (len(candidates[index]), index)):
        assign(prediction_index, set())
    true_positive = len(assigned_label)
    false_positive = len(predictions) - true_positive
    false_negative = len(labels) - true_positive
    precision = true_positive / len(predictions) if predictions else 0.0
    recall = true_positive / len(labels) if labels else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_by_type(
    predictions: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    *,
    tolerance_s: float = 1.0,
) -> dict[str, dict[str, float | int]]:
    return {
        kind: evaluate_events(
            [item for item in predictions if item.get("type") == kind],
            [item for item in labels if item.get("type") == kind],
            tolerance_s=tolerance_s,
        )
        for kind in ("crossing", "stop")
    }
