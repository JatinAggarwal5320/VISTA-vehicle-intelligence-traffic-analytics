"""Run VISTA on a fixed-camera video and save auditable event records."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
from time import perf_counter
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from vista_events import CrossingEvent, EventEngine, StopEvent, TrackPoint, Zone


VEHICLE_CLASSES = (2, 3, 5, 7)  # COCO: car, motorcycle, bus, truck


@dataclass(frozen=True)
class RunConfig:
    line_axis: str = "y"
    line_at: float = 0.60
    zone: tuple[float, float, float, float] = (0.05, 0.05, 0.95, 0.90)
    model: str = "yolo26s.pt"
    tracker: str = "botsort.yaml"
    confidence: float = 0.25
    stop_seconds: float = 2.0
    max_stationary_speed_px_s: float = 8.0
    line_margin_px: float = 5.0
    max_frames: int | None = None
    device: str | None = None

    def validate(self) -> None:
        if self.line_axis not in ("x", "y"):
            raise ValueError("line_axis must be x or y")
        if not 0 < self.line_at < 1:
            raise ValueError("line_at must be between 0 and 1")
        x1, y1, x2, y2 = self.zone
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("zone must be normalized x1,y1,x2,y2")
        if not 0 < self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.max_frames is not None and self.max_frames <= 0:
            raise ValueError("max_frames must be positive")


def _open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY, source TEXT NOT NULL, model TEXT NOT NULL,
            tracker TEXT NOT NULL, fps REAL NOT NULL, width INTEGER NOT NULL,
            height INTEGER NOT NULL, frames INTEGER NOT NULL, config_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
            time_s REAL NOT NULL, track_id INTEGER NOT NULL, type TEXT NOT NULL,
            vehicle_class TEXT NOT NULL, direction TEXT, duration_s REAL
        );
        CREATE TABLE IF NOT EXISTS samples (
            run_id INTEGER NOT NULL REFERENCES runs(id), time_s REAL NOT NULL,
            stopped_count INTEGER NOT NULL, PRIMARY KEY (run_id, time_s)
        );
    """)
    return db


def _draw_overlay(frame, boxes, engine: EventEngine, config: RunConfig, zone: Zone, time_s: float):
    import cv2

    height, width = frame.shape[:2]
    tint = frame.copy()
    cv2.rectangle(tint, (int(zone.x_min), int(zone.y_min)),
                  (int(zone.x_max), int(zone.y_max)), (218, 190, 54), -1)
    cv2.addWeighted(tint, 0.08, frame, 0.92, 0, frame)
    cv2.rectangle(frame, (int(zone.x_min), int(zone.y_min)),
                  (int(zone.x_max), int(zone.y_max)), (218, 190, 54), 2)
    if config.line_axis == "x":
        x = round(config.line_at * width)
        cv2.line(frame, (x, 0), (x, height), (20, 210, 225), 3)
    else:
        y = round(config.line_at * height)
        cv2.line(frame, (0, y), (width, y), (20, 210, 225), 3)
    for box in boxes:
        x1, y1, x2, y2, track_id, label, confidence = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (8, 190, 158), 2)
        caption = f"{label} #{track_id} {confidence:.2f}"
        cv2.putText(frame, caption, (x1, max(18, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 3)
        cv2.putText(frame, caption, (x1, max(18, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (14, 48, 57), 1)
        cv2.circle(frame, ((x1 + x2) // 2, y2), 3, (20, 210, 225), -1)
    header = f"VISTA  {time_s:05.1f}s  crossings {len(engine.crossings)}  visibly stopped {engine.stopped_count(time_s)}"
    cv2.rectangle(frame, (0, 0), (width, 36), (11, 31, 42), -1)
    cv2.putText(frame, header, (12, 25), cv2.FONT_HERSHEY_SIMPLEX,
                0.58, (255, 255, 255), 2)
    return frame


def process_video(
    video_path: Path,
    output_dir: Path,
    config: RunConfig,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Analyze a clip. The video, database, CSV, JSON and HTML are written together."""
    import cv2
    from ultralytics import YOLO

    from dashboard import write_dashboard

    config.validate()
    video_path = video_path.expanduser().resolve()
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise ValueError("Video has invalid frame rate or dimensions")
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if config.max_frames is not None:
        total_frames = min(total_frames, config.max_frames) if total_frames > 0 else config.max_frames

    x1, y1, x2, y2 = config.zone
    zone = Zone(x1 * width, y1 * height, x2 * width, y2 * height)
    line = config.line_at * (width if config.line_axis == "x" else height)
    engine = EventEngine(
        line_x=line if config.line_axis == "x" else None,
        line_y=line if config.line_axis == "y" else None,
        stop_zone=zone,
        line_margin_px=config.line_margin_px,
        max_stationary_speed_px_s=config.max_stationary_speed_px_s,
        min_stop_s=config.stop_seconds,
    )

    raw_video = output_dir / "annotated_raw.mp4"
    writer = cv2.VideoWriter(str(raw_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Could not create output video")
    started = perf_counter()
    model = YOLO(config.model)
    db = _open_db(output_dir / "events.sqlite")
    cursor = db.execute(
        "INSERT INTO runs(source,model,tracker,fps,width,height,frames,config_json) VALUES(?,?,?,?,?,?,?,?)",
        (video_path.name, config.model, config.tracker, fps, width, height, 0, json.dumps(asdict(config))),
    )
    run_id = cursor.lastrowid
    frames = 0
    tracked_boxes = 0
    unique_tracks: set[int] = set()
    last_sample_second = -1
    tracks_file = (output_dir / "tracks.csv").open("w", newline="")
    tracks_writer = csv.DictWriter(
        tracks_file,
        fieldnames=["frame", "time_s", "track_id", "vehicle_class", "confidence", "x1", "y1", "x2", "y2"],
    )
    tracks_writer.writeheader()
    try:
        while config.max_frames is None or frames < config.max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            time_s = frames / fps
            kwargs = dict(persist=True, tracker=config.tracker, classes=list(VEHICLE_CLASSES),
                          conf=config.confidence, verbose=False)
            if config.device:
                kwargs["device"] = config.device
            result = model.track(frame, **kwargs)[0]
            drawn_boxes = []
            boxes = result.boxes
            if boxes is not None and boxes.id is not None:
                for index in range(len(boxes)):
                    track_id = int(boxes.id[index].item())
                    class_id = int(boxes.cls[index].item())
                    label = model.names[class_id]
                    confidence = float(boxes.conf[index].item())
                    x1b, y1b, x2b, y2b = [int(v) for v in boxes.xyxy[index].tolist()]
                    drawn_boxes.append((x1b, y1b, x2b, y2b, track_id, label, confidence))
                    tracks_writer.writerow({
                        "frame": frames + 1, "time_s": round(time_s, 3), "track_id": track_id,
                        "vehicle_class": label, "confidence": round(confidence, 3),
                        "x1": x1b, "y1": y1b, "x2": x2b, "y2": y2b,
                    })
                    tracked_boxes += 1
                    unique_tracks.add(track_id)
                    point = TrackPoint(time_s, track_id, (x1b + x2b) / 2, y2b, label)
                    for event in engine.update(point):
                        event_type = "crossing" if isinstance(event, CrossingEvent) else "stop"
                        db.execute(
                            "INSERT INTO events(run_id,time_s,track_id,type,vehicle_class,direction,duration_s) "
                            "VALUES(?,?,?,?,?,?,?)",
                            (run_id, event.time_s, track_id, event_type, event.vehicle_class,
                             event.direction if event_type == "crossing" else None,
                             event.duration_s if isinstance(event, StopEvent) else None),
                        )
            second = int(time_s)
            if second > last_sample_second:
                db.execute("INSERT INTO samples(run_id,time_s,stopped_count) VALUES(?,?,?)",
                           (run_id, float(second), engine.stopped_count(time_s)))
                last_sample_second = second
            writer.write(_draw_overlay(frame, drawn_boxes, engine, config, zone, time_s))
            frames += 1
            if progress is not None and (frames == 1 or frames % 5 == 0 or frames == total_frames):
                progress(frames, total_frames)
    finally:
        capture.release()
        writer.release()
        tracks_file.close()
        db.execute("UPDATE runs SET frames=? WHERE id=?", (frames, run_id))
        db.commit()
        db.close()

    if frames == 0:
        raise ValueError("Video contained no decodable frames")
    playable_video = _make_browser_video(raw_video, output_dir / "annotated.mp4")
    processing_s = round(perf_counter() - started, 2)
    events = [dict(type="crossing", **asdict(e)) for e in engine.crossings]
    events += [dict(type="stop", **asdict(e)) for e in engine.stops]
    events.sort(key=lambda e: e["time_s"])
    counts = Counter(e["direction"] for e in events if e["type"] == "crossing")
    summary = {
        "source": video_path.name,
        "model": config.model,
        "tracker": config.tracker,
        "fps": fps,
        "width": width,
        "height": height,
        "frames": frames,
        "tracked_boxes": tracked_boxes,
        "unique_tracks": len(unique_tracks),
        "duration_s": round(frames / fps, 2),
        "processing_s": processing_s,
        "processing_fps": round(frames / processing_s, 2) if processing_s > 0 else None,
        "video": playable_video.name,
        "crossings": len(engine.crossings),
        "stops": len(engine.stops),
        "by_direction": dict(counts),
        "config": asdict(config),
        "events": events,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (output_dir / "events.csv").open("w", newline="") as file:
        csv_writer = csv.DictWriter(file, fieldnames=["type", "time_s", "track_id", "vehicle_class", "direction", "duration_s"])
        csv_writer.writeheader()
        for event in events:
            csv_writer.writerow(event)
    write_dashboard(summary, output_dir / "dashboard.html")
    return summary


def _make_browser_video(raw_video: Path, output_video: Path) -> Path:
    """Transcode to H.264 when bundled ffmpeg is available; retain raw MP4 otherwise."""
    try:
        import imageio_ffmpeg

        command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(raw_video),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", str(output_video)]
        subprocess.run(command, check=True, capture_output=True)
        raw_video.unlink()
        return output_video
    except (ImportError, OSError, subprocess.CalledProcessError):
        return raw_video
