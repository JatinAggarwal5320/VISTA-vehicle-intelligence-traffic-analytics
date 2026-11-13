"""VISTA's custom Python web interface. Run: python web_app.py"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file, url_for

from decision_engine import STATUSES, load_statuses, observation_action, save_status, traffic_action, traffic_brief_html
from evaluation import evaluate_by_type
from evaluate_run import read_labels
from observations import CATEGORIES, add_record, file_sha256, frame_at, issue_counts, load_records, marked_jpeg, pattern_for, report_html
from video_pipeline import RunConfig, process_video


HERE = Path(__file__).resolve().parent
SOURCE_DATA = {
    "signal": ("Signalized junction", "colonel_by_signal_10fps.mp4", "20 s · fixed camera · CC0"),
    "overhead": ("Overhead road", "intel_car_detection.mp4", "30 s · elevated view · CC BY 4.0"),
    "cuttack": ("Cuttack, India", "cuttack_link_road_30s.mp4", "30 s · fixed junction view · CC BY-SA 3.0"),
    "bengaluru": ("Bengaluru, India", "bengaluru_night_20s.mp4", "20 s · night congestion · CC BY-SA 4.0"),
    "pothole": ("Road defect reference", "kumasi_pothole_10fps.mp4", "20.7 s · crowded road · CC BY-SA 4.0"),
    "stop": ("Synthetic stop rule", "stopped_demo.mp4", "6 s · frozen frame · synthetic"),
}
POTHOLE_URL = "https://commons.wikimedia.org/wiki/File:Cars_Moving_into_pothole.webm"
FINAL_RUNS = {
    "colonel_by_yolo26s_final", "colonel_by_yolov8n_baseline",
    "intel_yolo26s_measured", "intel_yolov8n_baseline",
    "kumasi_pothole_yolo26s", "stopped_yolo26s",
    "cuttack_yolo26s", "bengaluru_night_yolo26s",
}
AUDITED_RUNS = {"colonel_by_yolo26s_final", "colonel_by_yolov8n_baseline",
                "intel_yolo26s_measured", "intel_yolov8n_baseline"}
RUN_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def create_app(data_dir: Path | None = None, process_fn=process_video) -> Flask:
    data = (data_dir or HERE).resolve()
    app = Flask(__name__, template_folder=str(HERE / "web_ui" / "templates"),
                static_folder=str(HERE / "web_ui" / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024
    runs = data / "runs"
    observations = data / "observations"
    actions_folder = data / "actions"
    samples = data / "sample_data"
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vista-model")
    jobs: dict[str, dict] = {}
    jobs_lock = threading.Lock()
    app.extensions["vista_jobs"] = jobs

    def run_folder(run_id: str) -> Path:
        if not RUN_NAME.fullmatch(run_id):
            abort(404)
        folder = runs / run_id
        if not (folder / "summary.json").is_file():
            abort(404)
        return folder

    def run_rows() -> list[dict]:
        rows = []
        for summary_path in runs.glob("*/summary.json"):
            try:
                summary = json.loads(summary_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            rows.append({
                "id": summary_path.parent.name,
                "summary": summary,
                "featured": summary_path.parent.name in FINAL_RUNS,
                "audited": summary_path.parent.name in AUDITED_RUNS,
                "model_label": Path(summary["model"]).stem.replace("yolo26s", "YOLO26s").replace("yolov8n", "YOLOv8n"),
                "modified": summary_path.stat().st_mtime,
            })
        return sorted(rows, key=lambda row: (not row["featured"], -row["modified"]))

    def source_video_for(folder: Path, summary: dict) -> tuple[Path, bool]:
        original = folder / summary["source"]
        sample = samples / summary["source"]
        if original.is_file():
            return original, True
        if sample.is_file():
            return sample, True
        return folder / summary["video"], False

    def video_duration(path: Path) -> float:
        import cv2
        capture = cv2.VideoCapture(str(path))
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            return capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else 0.0
        finally:
            capture.release()

    def parsed_float(form, name: str, default: float) -> float:
        value = form.get(name, "")
        return float(value) if value != "" else default

    def labels_for(folder: Path) -> list[dict]:
        path = folder / "manual_labels.json"
        return json.loads(path.read_text()) if path.exists() else []

    def action_rows() -> list[dict]:
        statuses = load_statuses(actions_folder)
        rows = []
        for row in run_rows():
            # Baseline and synthetic runs are benchmark controls, not site leads.
            if row["id"] in ("colonel_by_yolov8n_baseline", "intel_yolov8n_baseline", "stopped_yolo26s", "intel_demo"):
                continue
            if not row["featured"] and not row["id"].startswith("run_"):
                continue
            action = traffic_action(row["id"], row["summary"], labels_for(runs / row["id"]), audited=row["audited"])
            action["place"] = row["summary"]["source"].replace("_", " ")
            action["url"] = url_for("run_detail", run_id=row["id"])
            rows.append(action)
        records = load_records(observations)
        for record in records:
            action = observation_action(record, pattern_for(record, records))
            action["place"] = record["location"]
            action["url"] = url_for("observation_detail", obs_id=record["id"])
            rows.append(action)
        for action in rows:
            action["review"] = statuses.get(action["id"], {"status": "open", "note": "", "updated_at": ""})
        return rows

    @app.context_processor
    def common() -> dict:
        return {"project_name": "VISTA", "source_data": SOURCE_DATA}

    @app.get("/")
    def overview():
        rows = run_rows()
        featured = next((row for row in rows if row["id"] == "colonel_by_yolo26s_final"), rows[0] if rows else None)
        records = load_records(observations)
        benchmark_path = data / "evaluation_data" / "benchmark_results.json"
        benchmark = json.loads(benchmark_path.read_text()) if benchmark_path.exists() else None
        return render_template("overview.html", page="overview", featured=featured,
                               runs=rows[:5], records=records, benchmark=benchmark,
                               open_actions=sum(a["review"]["status"] == "open" for a in action_rows()))

    @app.get("/actions")
    def actions_page():
        rows = action_rows()
        return render_template("actions.html", page="actions", actions=rows,
                               counts={status: sum(a["review"]["status"] == status for a in rows) for status in STATUSES},
                               error=request.args.get("error"))

    @app.post("/actions/<kind>/<source_id>/status")
    def action_status(kind: str, source_id: str):
        action_id = f"{kind}:{source_id}"
        if action_id not in {row["id"] for row in action_rows()}:
            abort(404)
        status = request.form.get("status", "")
        note = request.form.get("note", "").strip()
        try:
            if status in ("referred", "closed") and not note:
                raise ValueError("Add a note describing the referral or closure before changing status.")
            save_status(actions_folder, action_id, status, note, datetime.now().astimezone().isoformat(timespec="seconds"))
        except ValueError as error:
            return redirect(url_for("actions_page", error=str(error)) + f"#{kind}-{source_id}")
        return redirect(url_for("actions_page") + f"#{kind}-{source_id}")

    @app.get("/analyze")
    def analyze_page():
        selected = request.args.get("source", "signal")
        if selected not in SOURCE_DATA and selected != "upload":
            selected = "signal"
        return render_template("analyze.html", page="analyze", selected=selected,
                               sources=SOURCE_DATA, error=request.args.get("error"))

    @app.post("/api/jobs")
    def start_job():
        form = request.form
        source_key = form.get("source", "signal")
        if source_key not in SOURCE_DATA and source_key != "upload":
            return jsonify(error="Choose a valid video source."), 400
        try:
            axis = form.get("axis", "y")
            line_at = parsed_float(form, "line_at", .60)
            confidence = parsed_float(form, "confidence", .25)
            zone = tuple(parsed_float(form, key, default) for key, default in (
                ("zone_x1", .05), ("zone_y1", .05), ("zone_x2", .95), ("zone_y2", .90)))
            model_key = form.get("model", "yolo26s")
            if model_key not in ("yolo26s", "yolov8n"):
                raise ValueError("Choose a valid model")
            frame_limit = int(form.get("max_frames") or 0)
            config = RunConfig(
                line_axis=axis, line_at=line_at, zone=zone,
                model=str(data / f"{model_key}.pt"),
                confidence=confidence,
                stop_seconds=parsed_float(form, "stop_seconds", 2.0),
                max_stationary_speed_px_s=parsed_float(form, "stationary_px_s", 8.0),
                max_frames=frame_limit or None,
            )
            config.validate()
        except (ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400
        if source_key == "upload":
            uploaded = request.files.get("video")
            suffix = Path(uploaded.filename or "").suffix.lower() if uploaded else ""
            if not uploaded or suffix not in (".mp4", ".mov", ".avi", ".webm"):
                return jsonify(error="Upload an MP4, MOV, AVI, or WEBM video."), 400
        else:
            source = samples / SOURCE_DATA[source_key][1]
            if not source.is_file():
                return jsonify(error="The sample video is missing."), 400

        job_id = uuid.uuid4().hex[:12]
        run_id = f"run_{datetime.now():%Y%m%d_%H%M%S}_{job_id[:6]}"
        folder = runs / run_id
        folder.mkdir(parents=True)
        if source_key == "upload":
            source = folder / f"source{suffix}"
            uploaded.save(source)
        with jobs_lock:
            jobs[job_id] = {"status": "queued", "done": 0, "total": 0, "run_id": run_id}

        def work() -> None:
            with jobs_lock:
                jobs[job_id]["status"] = "running"

            def progress(done: int, total: int) -> None:
                with jobs_lock:
                    jobs[job_id].update(done=done, total=total)

            try:
                process_fn(source, folder, config, progress=progress)
            except Exception as error:
                with jobs_lock:
                    jobs[job_id].update(status="error", error=str(error))
            else:
                with jobs_lock:
                    jobs[job_id].update(status="complete", result_url=url_for_run(run_id))

        executor.submit(work)
        return jsonify(job_id=job_id, run_id=run_id), 202

    def url_for_run(run_id: str) -> str:
        return f"/runs/{run_id}"

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                abort(404)
            return jsonify(dict(job))

    @app.get("/samples/<source_key>")
    def sample_video(source_key: str):
        if source_key not in SOURCE_DATA:
            abort(404)
        return send_file(samples / SOURCE_DATA[source_key][1], conditional=True)

    @app.get("/runs")
    def runs_page():
        return render_template("runs.html", page="runs", runs=run_rows())

    @app.get("/runs/<run_id>")
    def run_detail(run_id: str):
        folder = run_folder(run_id)
        summary = json.loads((folder / "summary.json").read_text())
        labels = labels_for(folder)
        evaluation = evaluate_by_type(summary["events"], labels) if labels else None
        bins: dict[int, int] = {}
        for event in summary["events"]:
            if event["type"] == "crossing":
                bucket = int(event["time_s"] // 5) * 5
                bins[bucket] = bins.get(bucket, 0) + 1
        timeline = [{"start": second, "count": bins.get(second, 0)} for second in range(0, max(5, int(summary["duration_s"]) + 5), 5)]
        max_bin = max((item["count"] for item in timeline), default=1) or 1
        action = traffic_action(run_id, summary, labels, audited=run_id in AUDITED_RUNS)
        return render_template("run_detail.html", page="runs", run_id=run_id, summary=summary,
                               labels=labels, evaluation=evaluation, timeline=timeline,
                               max_bin=max_bin, has_tracks=(folder / "tracks.csv").is_file(),
                               action=action,
                               model_label=Path(summary["model"]).stem.replace("yolo26s", "YOLO26s").replace("yolov8n", "YOLOv8n"))

    @app.get("/runs/<run_id>/video")
    def run_video(run_id: str):
        folder = run_folder(run_id)
        summary = json.loads((folder / "summary.json").read_text())
        filename = Path(summary["video"]).name
        return send_file(folder / filename, conditional=True)

    @app.get("/runs/<run_id>/review-brief")
    def run_review_brief(run_id: str):
        import cv2
        folder = run_folder(run_id)
        summary = json.loads((folder / "summary.json").read_text())
        action = traffic_action(run_id, summary, labels_for(folder), audited=run_id in AUDITED_RUNS)
        capture = cv2.VideoCapture(str(folder / Path(summary["video"]).name))
        frame_jpeg = None
        try:
            if capture.isOpened():
                capture.set(cv2.CAP_PROP_POS_MSEC, ((action["window_start"] or 0) + 2) * 1000)
                ok, frame = capture.read()
                if ok:
                    ok, image = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ok:
                        frame_jpeg = image.tobytes()
        finally:
            capture.release()
        page = traffic_brief_html(action, summary, frame_jpeg)
        return Response(page, mimetype="text/html",
                        headers={"Content-Disposition": f'attachment; filename="{run_id}-review-brief.html"'})

    @app.get("/runs/<run_id>/download/<kind>")
    def run_download(run_id: str, kind: str):
        folder = run_folder(run_id)
        summary = json.loads((folder / "summary.json").read_text())
        names = {
            "video": Path(summary["video"]).name,
            "events": "events.csv",
            "tracks": "tracks.csv",
            "json": "summary.json",
            "sqlite": "events.sqlite",
            "dashboard": "dashboard.html",
            "labels": "manual_labels.json",
        }
        if kind not in names:
            abort(404)
        path = folder / names[kind]
        if not path.is_file():
            abort(404)
        return send_file(path, as_attachment=True, download_name=f"vista-{run_id}-{path.name}")

    @app.post("/runs/<run_id>/labels")
    def add_label(run_id: str):
        folder = run_folder(run_id)
        summary = json.loads((folder / "summary.json").read_text())
        try:
            time_s = float(request.form["time_s"])
            if not 0 <= time_s <= summary["duration_s"]:
                raise ValueError("Timestamp is outside the clip")
            kind = request.form["type"]
            if kind not in ("crossing", "stop"):
                raise ValueError("Choose crossing or stop")
            label = {"type": kind, "time_s": round(time_s, 2)}
            if kind == "crossing":
                direction = request.form.get("direction", "")
                choices = ("top_to_bottom", "bottom_to_top") if summary["config"]["line_axis"] == "y" else ("left_to_right", "right_to_left")
                if direction not in choices:
                    raise ValueError("Choose a valid direction")
                label["direction"] = direction
            vehicle_class = request.form.get("vehicle_class", "")
            if vehicle_class:
                if vehicle_class not in ("car", "motorcycle", "bus", "truck"):
                    raise ValueError("Choose a valid vehicle class")
                label["vehicle_class"] = vehicle_class
        except (ValueError, KeyError) as error:
            return redirect(url_for("run_detail", run_id=run_id, error=str(error)) + "#validation")
        labels = labels_for(folder)
        labels.append(label)
        labels.sort(key=lambda item: item["time_s"])
        (folder / "manual_labels.json").write_text(json.dumps(labels, indent=2) + "\n")
        return redirect(url_for("run_detail", run_id=run_id) + "#validation")

    @app.post("/runs/<run_id>/labels/import")
    def import_labels(run_id: str):
        folder = run_folder(run_id)
        upload = request.files.get("labels")
        if not upload or Path(upload.filename or "").suffix.lower() != ".csv":
            return redirect(url_for("run_detail", run_id=run_id, error="Choose a labels CSV") + "#validation")
        path = folder / "imported_labels.csv"
        upload.save(path)
        try:
            labels = read_labels(path)
        except (ValueError, KeyError, UnicodeError) as error:
            path.unlink(missing_ok=True)
            return redirect(url_for("run_detail", run_id=run_id, error=str(error)) + "#validation")
        (folder / "manual_labels.json").write_text(json.dumps(labels, indent=2) + "\n")
        return redirect(url_for("run_detail", run_id=run_id) + "#validation")

    @app.get("/benchmark")
    def benchmark_page():
        path = data / "evaluation_data" / "benchmark_results.json"
        report = json.loads(path.read_text()) if path.exists() else None
        return render_template("benchmark.html", page="benchmark", report=report)

    @app.get("/observations")
    def observations_page():
        records = load_records(observations)
        return render_template("observations.html", page="observations", records=list(reversed(records)),
                               counts=issue_counts(records))

    def observation_record(obs_id: str) -> dict:
        if not RUN_NAME.fullmatch(obs_id):
            abort(404)
        record = next((item for item in load_records(observations) if item["id"] == obs_id), None)
        if record is None:
            abort(404)
        return record

    @app.get("/observations/new")
    def observation_new():
        source = request.args.get("source", "public")
        if source not in ("public", "run", "photo"):
            source = "public"
        return render_template("observation_new.html", page="observations", source=source,
                               runs=run_rows(), categories=CATEGORIES, error=None, form={})

    @app.post("/observations/new")
    def observation_create():
        source = request.form.get("source", "public")
        if source not in ("public", "run", "photo"):
            abort(400)
        form = request.form
        try:
            box = tuple(float(form[key]) / 100 for key in ("box_left", "box_top", "box_right", "box_bottom"))
            details = {
                "category": form.get("category", ""),
                "location": form.get("location", "").strip(),
                "description": form.get("description", "").strip(),
                "precise_location": form.get("precise_location") == "yes",
                "media_date": form.get("media_date", "").strip(),
                "source_kind": form.get("source_kind", "Source unknown"),
                "source_credit": form.get("source_credit", "").strip(),
                "source_url": form.get("source_url", "").strip(),
                "video_time_s": None,
                "mark_box": list(box),
            }
            original_media = None
            suffix = ".jpg"
            if source == "public":
                video = samples / SOURCE_DATA["pothole"][1]
                details.update(
                    source_kind="Public reference", source_url=POTHOLE_URL,
                    source_credit="Amuzujoe / Wikimedia Commons · CC BY-SA 4.0; 10 fps MP4 conversion",
                    media_date="2020-02-26", precise_location=False,
                    media_key=POTHOLE_URL, media_file=str(video.relative_to(data)),
                )
                seconds = float(form.get("video_time_s", "12"))
                frame = frame_at(video, seconds)
                details["video_time_s"] = seconds
            elif source == "run":
                folder = run_folder(form.get("run_id", ""))
                summary = json.loads((folder / "summary.json").read_text())
                video, is_original = source_video_for(folder, summary)
                details["media_key"] = file_sha256(video) if is_original else f"source-unavailable:{summary['source']}"
                details["media_file"] = str(video.relative_to(data))
                seconds = float(form.get("video_time_s", "0"))
                frame = frame_at(video, seconds)
                details["video_time_s"] = seconds
            else:
                import cv2
                import numpy as np
                upload = request.files.get("photo")
                suffix = Path(upload.filename or "").suffix.lower() if upload else ""
                if not upload or suffix not in (".jpg", ".jpeg", ".png"):
                    raise ValueError("Upload a JPG or PNG photo")
                original_media = upload.read()
                if len(original_media) > 20 * 1024 * 1024:
                    raise ValueError("Photo must be under 20 MB")
                frame = cv2.imdecode(np.frombuffer(original_media, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("Photo could not be decoded")
                details["media_key"] = hashlib.sha256(original_media).hexdigest()
            evidence = marked_jpeg(frame, box)
            record = add_record(observations, details, evidence, original_media=original_media, original_suffix=suffix)
        except (ValueError, KeyError, OSError, RuntimeError) as error:
            return render_template("observation_new.html", page="observations", source=source,
                                   runs=run_rows(), categories=CATEGORIES, error=str(error), form=form), 400
        return redirect(url_for("observation_detail", obs_id=record["id"]))

    @app.get("/observations/<obs_id>")
    def observation_detail(obs_id: str):
        record = observation_record(obs_id)
        all_records = load_records(observations)
        pattern = pattern_for(record, all_records)
        return render_template("observation_detail.html", page="observations", record=record,
                               pattern=pattern, action=observation_action(record, pattern))

    @app.get("/observations/<obs_id>/evidence")
    def observation_evidence(obs_id: str):
        record = observation_record(obs_id)
        return send_file(observations / record["evidence_file"], conditional=True)

    @app.get("/observations/<obs_id>/report")
    def observation_report(obs_id: str):
        record = observation_record(obs_id)
        records = load_records(observations)
        evidence = (observations / record["evidence_file"]).read_bytes()
        page = report_html(record, records, evidence)
        return Response(page, mimetype="text/html",
                        headers={"Content-Disposition": f'attachment; filename="{obs_id}-report.html"'})

    @app.get("/health")
    def health():
        return jsonify(status="ok", engine="Python / Ultralytics YOLO + BoT-SORT")

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="Upload exceeds the 250 MB limit."), 413

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8501, threaded=True, debug=False)
