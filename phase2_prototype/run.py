"""Command-line entry point for processing a fixed-camera traffic clip."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_pipeline import RunConfig, process_video


def main() -> None:
    parser = argparse.ArgumentParser(description="VISTA vehicle crossing and visible-stop analysis")
    parser.add_argument("video", type=Path, help="Local MP4/MOV/AVI traffic video")
    parser.add_argument("--output", type=Path, default=Path("runs/latest"), help="Output directory")
    parser.add_argument("--axis", choices=("x", "y"), default="y", help="x = vertical line; y = horizontal line")
    parser.add_argument("--line", type=float, default=0.60, help="Counting line position, 0-1 of frame")
    parser.add_argument("--zone", default="0.05,0.05,0.95,0.90", help="Stop zone as normalized x1,y1,x2,y2")
    parser.add_argument("--model", default="yolo26s.pt", help="Ultralytics checkpoint or path")
    parser.add_argument("--tracker", default="botsort.yaml", help="Ultralytics tracking config")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--stop-seconds", type=float, default=2.0)
    parser.add_argument("--stationary-px-s", type=float, default=8.0)
    parser.add_argument("--max-frames", type=int, help="Limit processing for a quick test")
    parser.add_argument("--device", help="Inference device, e.g. cpu or mps")
    args = parser.parse_args()
    try:
        zone = tuple(float(part.strip()) for part in args.zone.split(","))
        if len(zone) != 4:
            raise ValueError
    except ValueError:
        parser.error("--zone needs four comma-separated numbers")
    config = RunConfig(
        line_axis=args.axis, line_at=args.line, zone=zone, model=args.model,
        tracker=args.tracker, confidence=args.confidence, stop_seconds=args.stop_seconds,
        max_stationary_speed_px_s=args.stationary_px_s, max_frames=args.max_frames,
        device=args.device,
    )
    summary = process_video(args.video, args.output, config)
    print(json.dumps({key: summary[key] for key in ("source", "frames", "duration_s", "crossings", "stops", "by_direction")}, indent=2))
    print(f"Dashboard: {(args.output / 'dashboard.html').resolve()}")


if __name__ == "__main__":
    main()
