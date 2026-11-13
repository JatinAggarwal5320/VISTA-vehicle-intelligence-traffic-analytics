"""Rebuild the two-clip, manually audited VISTA comparison from saved runs."""

from __future__ import annotations

import json
import platform
from importlib.metadata import version
from pathlib import Path

from evaluate_run import read_labels
from evaluation import evaluate_by_type


HERE = Path(__file__).resolve().parent
CASES = [
    (
        "Overhead road",
        "intel_crossings.csv",
        {"YOLOv8n baseline": "intel_yolov8n_baseline", "YOLO26s primary": "intel_yolo26s_measured"},
    ),
    (
        "Traffic signal",
        "colonel_by_crossings.csv",
        {"YOLOv8n baseline": "colonel_by_yolov8n_baseline", "YOLO26s primary": "colonel_by_yolo26s_final"},
    ),
]


def rebuild() -> dict:
    report = {
        "method": "One-to-one event matching by type, direction, vehicle class and timestamp within ±1 second",
        "annotation_limit": "Two short clips, one visual reviewer, 11 crossing labels. No real stop labels. Not a general accuracy estimate.",
        "environment": {
            "python": platform.python_version(), "system": platform.system(),
            "machine": platform.machine(), "ultralytics": version("ultralytics"),
        },
        "clips": [],
        "overall": {},
    }
    totals = {name: {"tp": 0, "fp": 0, "fn": 0, "processing_s": 0.0, "frames": 0} for name in CASES[0][2]}
    for scene, label_name, runs in CASES:
        labels = read_labels(HERE / "evaluation_data" / label_name)
        clip = {"scene": scene, "manual_crossings": len(labels), "models": {}}
        for model_name, folder_name in runs.items():
            summary = json.loads((HERE / "runs" / folder_name / "summary.json").read_text())
            result = evaluate_by_type(summary["events"], labels)["crossing"]
            clip["models"][model_name] = {
                "checkpoint": Path(summary["model"]).name,
                "predicted_crossings": summary["crossings"],
                "tp": result["tp"], "fp": result["fp"], "fn": result["fn"],
                "precision": result["precision"], "recall": result["recall"], "f1": result["f1"],
                "processing_s": summary.get("processing_s"), "frames": summary["frames"],
            }
            total = totals[model_name]
            for field in ("tp", "fp", "fn", "frames"):
                total[field] += clip["models"][model_name][field]
            total["processing_s"] += summary.get("processing_s") or 0.0
        report["clips"].append(clip)
    for model_name, total in totals.items():
        precision = total["tp"] / (total["tp"] + total["fp"]) if total["tp"] + total["fp"] else 0.0
        recall = total["tp"] / (total["tp"] + total["fn"]) if total["tp"] + total["fn"] else 0.0
        report["overall"][model_name] = {
            **total,
            "processing_s": round(total["processing_s"], 2),
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    output = HERE / "evaluation_data" / "benchmark_results.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    report = rebuild()
    print("Scene | Model | Manual | Predicted | Matched | Extra | Missed | Precision | Recall | Time")
    print("--- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:")
    for clip in report["clips"]:
        for name, result in clip["models"].items():
            print(f"{clip['scene']} | {name} | {clip['manual_crossings']} | {result['predicted_crossings']} | "
                  f"{result['tp']} | {result['fp']} | {result['fn']} | {result['precision']:.0%} | "
                  f"{result['recall']:.0%} | {result['processing_s']:.2f}s")
    for name, result in report["overall"].items():
        print(f"Both clips | {name} | 11 | {result['tp'] + result['fp']} | {result['tp']} | "
              f"{result['fp']} | {result['fn']} | {result['precision']:.0%} | "
              f"{result['recall']:.0%} | {result['processing_s']:.2f}s")


if __name__ == "__main__":
    main()
