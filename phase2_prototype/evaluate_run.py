"""Compare one or more VISTA run summaries with manually labeled events."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from evaluation import evaluate_by_type


def read_labels(path: Path) -> list[dict]:
    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))
    labels = []
    for row in rows:
        kind = row["type"].strip()
        if kind not in ("crossing", "stop"):
            raise ValueError(f"Unsupported label type: {kind}")
        label = {"type": kind, "time_s": float(row["time_s"])}
        if kind == "crossing":
            direction = row["direction"].strip()
            if direction not in ("left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"):
                raise ValueError(f"Invalid crossing direction: {direction}")
            label["direction"] = direction
        if row.get("vehicle_class", "").strip():
            label["vehicle_class"] = row["vehicle_class"].strip()
        labels.append(label)
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True, help="Manual event CSV")
    parser.add_argument("--tolerance", type=float, default=1.0, help="Maximum timestamp difference in seconds")
    parser.add_argument("--output", type=Path, help="Write machine-readable comparison JSON")
    parser.add_argument("summaries", type=Path, nargs="+", help="One or more VISTA summary.json files")
    args = parser.parse_args()
    labels = read_labels(args.labels)
    report = {"labels": str(args.labels), "label_count": len(labels), "tolerance_s": args.tolerance, "runs": []}
    print("Model | Crossings | TP | FP | FN | Precision | Recall | F1 | Processing")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:")
    for path in args.summaries:
        summary = json.loads(path.read_text())
        scores = evaluate_by_type(summary["events"], labels, tolerance_s=args.tolerance)
        score = scores["crossing"]
        run = {
            "summary": str(path), "source": summary["source"], "model": Path(summary["model"]).name,
            "tracker": summary["tracker"], "frames": summary["frames"],
            "processing_s": summary.get("processing_s"), "counts": {"crossings": summary["crossings"], "stops": summary["stops"]},
            "scores": scores,
        }
        report["runs"].append(run)
        seconds = f"{run['processing_s']:.2f}s" if run["processing_s"] is not None else "—"
        print(f"{run['model']} | {summary['crossings']} | {score['tp']} | {score['fp']} | {score['fn']} | "
              f"{score['precision']:.0%} | {score['recall']:.0%} | {score['f1']:.0%} | {seconds}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
