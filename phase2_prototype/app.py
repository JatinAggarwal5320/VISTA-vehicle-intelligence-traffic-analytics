"""Python-first VISTA review app. Run with: streamlit run app.py"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from evaluation import evaluate_by_type
from evaluate_run import read_labels
from observations import CATEGORIES, add_record, file_sha256, frame_at, issue_counts, load_records, marked_jpeg, pattern_for, report_html
from video_pipeline import RunConfig, process_video


HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
MOVING_SAMPLE = HERE / "sample_data" / "intel_car_detection.mp4"
SIGNAL_SAMPLE = HERE / "sample_data" / "colonel_by_signal_10fps.mp4"
STOP_SAMPLE = HERE / "sample_data" / "stopped_demo.mp4"
POTHOLE_SAMPLE = HERE / "sample_data" / "kumasi_pothole_10fps.mp4"
POTHOLE_URL = "https://commons.wikimedia.org/wiki/File:Cars_Moving_into_pothole.webm"
OBSERVATIONS = HERE / "observations"
MODELS = {"YOLO26s · primary": HERE / "yolo26s.pt", "YOLOv8n · baseline": HERE / "yolov8n.pt"}


def saved_runs() -> list[Path]:
    if not RUNS.exists():
        return []
    return sorted(
        (path.parent for path in RUNS.glob("*/summary.json")),
        key=lambda path: (path / "summary.json").stat().st_mtime,
        reverse=True,
    )


def load_labels(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def labels_csv(labels: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["type", "time_s", "direction", "vehicle_class"])
    writer.writeheader()
    for label in labels:
        writer.writerow(label)
    return output.getvalue()


def run_analysis(source: Path, config: RunConfig, uploaded_file=None) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    folder = RUNS / f"run_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    folder.mkdir()
    if uploaded_file is not None:
        suffix = Path(uploaded_file.name).suffix.lower()
        source = folder / f"source{suffix}"
        uploaded_file.seek(0)
        with source.open("wb") as output:
            shutil.copyfileobj(uploaded_file, output)

    bar = st.progress(0, text=f"Loading {Path(config.model).stem} and BoT-SORT…")

    def update_progress(done: int, total: int) -> None:
        fraction = min(1.0, done / total) if total > 0 else 0.0
        bar.progress(fraction, text=f"Tracking vehicles: {done} / {total or '?'} frames")

    try:
        with st.spinner("Running detection, tracking, event rules and video export…"):
            process_video(source, folder, config, progress=update_progress)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    bar.progress(1.0, text="Analysis complete")
    st.session_state.active_run = str(folder)
    st.rerun()


def render_results(folder: Path) -> None:
    summary = json.loads((folder / "summary.json").read_text())
    events = summary["events"]
    st.divider()
    st.subheader("Review the run")
    st.caption(
        f"{summary['source']} · {summary['duration_s']:.1f}s · "
        f"{summary['frames']} frames · {Path(summary['model']).name} + {summary['tracker']}"
    )
    metrics = st.columns(4)
    metrics[0].metric("Directional crossings", summary["crossings"])
    metrics[1].metric("Visible stops", summary["stops"])
    metrics[2].metric("Analyzed frames", summary["frames"])
    metrics[3].metric("Clip duration", f"{summary['duration_s']:.1f}s")
    if summary.get("processing_s") is not None:
        st.caption(f"Processing time: {summary['processing_s']:.1f}s · {summary['processing_fps']:.1f} analyzed frames/s on this machine")

    video_col, event_col = st.columns([1.35, 1], gap="large")
    with video_col:
        st.markdown("**Annotated footage**")
        video_path = folder / summary["video"]
        if video_path.exists():
            st.video(str(video_path))
        else:
            st.warning("Annotated video is missing from this run.")
    with event_col:
        st.markdown("**Events by direction**")
        if summary["by_direction"]:
            chart = pd.DataFrame(
                [{"Direction": key.replace("_", " "), "Crossings": count}
                 for key, count in summary["by_direction"].items()]
            ).set_index("Direction")
            st.bar_chart(chart)
        else:
            st.info("No line crossings recorded in this clip.")
        st.caption("A visible stop means low image motion inside the marked zone. It is not measured road speed or delay.")

    st.markdown("**Event log**")
    if events:
        table = pd.DataFrame(events)
        table["time_s"] = table["time_s"].round(2)
        st.dataframe(table, hide_index=True, width="stretch")
    else:
        st.info("No events recorded. Try adjusting the line, zone or confidence for this camera.")

    downloads = st.columns(5)
    downloads[0].download_button("Events CSV", (folder / "events.csv").read_bytes(), "vista-events.csv", "text/csv")
    downloads[1].download_button("Run JSON", (folder / "summary.json").read_bytes(), "vista-run.json", "application/json")
    downloads[2].download_button("Annotated MP4", (folder / summary["video"]).read_bytes(), "vista-annotated.mp4", "video/mp4")
    downloads[3].download_button("SQLite data", (folder / "events.sqlite").read_bytes(), "vista-events.sqlite", "application/octet-stream")
    tracks_path = folder / "tracks.csv"
    if tracks_path.exists():
        downloads[4].download_button("Tracks CSV", tracks_path.read_bytes(), "vista-tracks.csv", "text/csv")

    with st.expander("Manual validation · compare against what you see", expanded=False):
        st.caption("Pause the annotated video, note each real crossing or visible stop, then enter its timestamp. Label the whole clip before treating precision and recall as accuracy results.")
        label_path = folder / "manual_labels.json"
        labels = load_labels(label_path)
        with st.form(f"label_form_{folder.name}", clear_on_submit=True):
            time_s = st.number_input("Video time (seconds)", min_value=0.0, max_value=float(summary["duration_s"]), step=0.1)
            kind = st.selectbox("Event", ["crossing", "stop"])
            directions = ["top_to_bottom", "bottom_to_top"] if summary["config"]["line_axis"] == "y" else ["left_to_right", "right_to_left"]
            direction = st.selectbox("Direction (crossings only)", directions)
            vehicle_class = st.selectbox("Vehicle class (optional)", ["Any", "car", "motorcycle", "bus", "truck"])
            added = st.form_submit_button("Add manual label")
        if added:
            label = {"type": kind, "time_s": round(time_s, 2)}
            if kind == "crossing":
                label["direction"] = direction
            if vehicle_class != "Any":
                label["vehicle_class"] = vehicle_class
            labels.append(label)
            labels.sort(key=lambda item: item["time_s"])
            label_path.write_text(json.dumps(labels, indent=2) + "\n")
            st.rerun()
        if labels:
            st.dataframe(pd.DataFrame(labels), hide_index=True, width="stretch")
            evaluation = evaluate_by_type(events, labels)
            for kind in ("crossing", "stop"):
                if not any(label["type"] == kind for label in labels):
                    continue
                result = evaluation[kind]
                st.write(
                    f"**{kind.title()} · ±1s:** precision {result['precision']:.0%}, "
                    f"recall {result['recall']:.0%} "
                    f"({result['tp']} matched, {result['fp']} extra, {result['fn']} missed)"
                )
            st.download_button("Manual labels CSV", labels_csv(labels), "vista-manual-labels.csv", "text/csv")
            if st.button("Remove last label"):
                labels.pop()
                label_path.write_text(json.dumps(labels, indent=2) + "\n")
                st.rerun()
        else:
            st.caption("No manual labels yet; the counts above are model outputs, not verified accuracy.")

        st.download_button("Blank labels CSV", "type,time_s,direction,vehicle_class\n", "vista-label-template.csv", "text/csv")
        uploaded_labels = st.file_uploader("Import reviewed labels CSV", type=["csv"], key=f"labels_{folder.name}")
        if uploaded_labels is not None and st.button("Import labels", key=f"import_{folder.name}"):
            imported_path = folder / "imported_labels.csv"
            imported_path.write_bytes(uploaded_labels.getvalue())
            try:
                imported = read_labels(imported_path)
            except (ValueError, KeyError) as error:
                st.error(f"Invalid labels CSV: {error}")
            else:
                label_path.write_text(json.dumps(imported, indent=2) + "\n")
                st.rerun()


def render_sample_comparison() -> None:
    reports = [
        ("Overhead road", HERE / "evaluation_data" / "intel_model_comparison.json"),
        ("Traffic signal", HERE / "evaluation_data" / "colonel_by_model_comparison.json"),
    ]
    if not all(path.exists() for _, path in reports):
        return
    rows = []
    for scene, path in reports:
        report = json.loads(path.read_text())
        for run in report["runs"]:
            score = run["scores"]["crossing"]
            rows.append({
                "Clip": scene, "Model": run["model"], "Crossings": run["counts"]["crossings"],
                "Matched": score["tp"], "Extra": score["fp"], "Missed": score["fn"],
                "Precision": f"{score['precision']:.0%}", "Recall": f"{score['recall']:.0%}",
                "Processing": f"{run['processing_s']:.1f}s" if run["processing_s"] is not None else "—",
            })
    with st.expander("Measured baseline comparison · two real clips", expanded=True):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Eleven manually reviewed line crossings across two clips, with ±1s matching. This is a small single-reviewer audit, not a general accuracy estimate. The stop demo uses a frozen frame and is excluded.")


def render_observations() -> None:
    st.header("Road observations")
    st.write("Mark an issue visible in a video or photo, keep its source and location, then download an evidence-backed report. The issue box and description are entered by a person; YOLO does not detect potholes.")
    records = load_records(OBSERVATIONS)
    if records:
        st.subheader("Recorded observations")
        st.dataframe(pd.DataFrame([{
            "ID": item["id"], "Issue": item["category"], "Location": item["location"],
            "Source": item["source_kind"], "Media date": item.get("media_date") or "Unknown",
        } for item in records]), hide_index=True, width="stretch")
        selected_id = st.selectbox("Open an observation", [item["id"] for item in reversed(records)])
        selected = next(item for item in records if item["id"] == selected_id)
        evidence = (OBSERVATIONS / selected["evidence_file"]).read_bytes()
        left, right = st.columns([1.2, 1], gap="large")
        with left:
            st.image(evidence, caption="Reviewer-marked evidence frame", width="stretch")
        with right:
            st.markdown(f"**{selected['category']}** · {selected['location']}")
            st.write(selected["description"])
            if selected.get("source_url"):
                st.link_button("Open credited source", selected["source_url"])
            pattern = pattern_for(selected, records)
            if pattern["recurrence_supported"]:
                st.success(f"Repeated observations: {pattern['observations']} records, {pattern['distinct_media']} media items, {pattern['distinct_media_dates']} source dates at this entered location.")
            else:
                st.info("Recurrence is not established. This location needs a second independent, dated observation.")
            st.download_button("Download road issue report (HTML)", report_html(selected, records, evidence),
                               f"{selected_id}-report.html", "text/html")
            st.download_button("Download evidence image", evidence, f"{selected_id}-evidence.jpg", "image/jpeg")
        st.caption("Issue totals in this local store: " + ", ".join(f"{name}: {count}" for name, count in issue_counts(records).items()))

    st.divider()
    st.subheader("Record another observation")
    source_choice = st.radio("Evidence source", ["Included public pothole video", "Saved VISTA run", "Upload a photo"], horizontal=True)
    source_video = None
    source_is_original = True
    photo = None
    if source_choice == "Included public pothole video":
        source_video = POTHOLE_SAMPLE
        st.video(str(source_video))
        st.caption("Real road footage near Kumasi, Ghana, by Amuzujoe · CC BY-SA 4.0. The exact road and junction are unknown. This is a public example, not footage captured by your team.")
    elif source_choice == "Saved VISTA run":
        folders = saved_runs()
        if folders:
            folder = st.selectbox("Choose a run", folders, format_func=lambda path: path.name)
            summary = json.loads((folder / "summary.json").read_text())
            original = folder / summary["source"]
            sample = HERE / "sample_data" / summary["source"]
            source_is_original = original.exists() or sample.exists()
            source_video = original if original.exists() else sample if sample.exists() else folder / summary["video"]
            st.video(str(source_video))
            st.caption("For uploaded clips, VISTA uses the stored source video. Older saved runs may only contain annotated output.")
        else:
            st.info("Analyze or upload a video in Traffic analysis first.")
    else:
        photo = st.file_uploader("Upload JPG or PNG evidence", type=["jpg", "jpeg", "png"], key="observation_photo")
        if photo is not None:
            st.image(photo, width="stretch")

    public = source_choice == "Included public pothole video"
    max_seconds = 0.0
    if source_video is not None:
        import cv2
        capture = cv2.VideoCapture(str(source_video))
        fps = capture.get(cv2.CAP_PROP_FPS)
        max_seconds = max(0.0, capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps - 0.1) if fps > 0 else 0.0
        capture.release()
    with st.form("new_observation"):
        category = st.selectbox("Issue category", CATEGORIES)
        location = st.text_input("Location as known", "Kumasi, Ghana (exact road unknown)" if public else "")
        precise_location = st.checkbox("I know the exact road or junction shown", value=False)
        description = st.text_area("What is visible?", "Broken and uneven road surface is visible in the near lane while vehicles pass. The clip does not establish whether this defect causes the congestion." if public else "")
        if source_video is not None:
            video_time = st.number_input("Evidence time in video (seconds)", min_value=0.0, max_value=max_seconds,
                                         value=min(12.0, max_seconds) if public else 0.0, step=0.1)
        else:
            video_time = None
        st.caption("Mark a rectangle around the issue using percentages of the frame. This is a manual mark, not model output.")
        a, b, c, d = st.columns(4)
        box = (
            a.number_input("Left %", 0, 99, 32 if public else 20),
            b.number_input("Top %", 0, 99, 72 if public else 20),
            c.number_input("Right %", 1, 100, 65 if public else 80),
            d.number_input("Bottom %", 1, 100, 91 if public else 80),
        )
        if public:
            source_kind = "Public reference"
            media_date = "2020-02-26"
            source_credit = "Amuzujoe / Wikimedia Commons · CC BY-SA 4.0; converted to 10 fps MP4 for VISTA"
            source_url = POTHOLE_URL
            st.caption(f"Source: {source_credit} · {source_url}")
        else:
            source_kind = st.selectbox("Media provenance", ["Source unknown", "Team captured (reporter declared)", "Public reference"])
            media_date = st.text_input("Media capture date, if known (YYYY-MM-DD)")
            source_credit = st.text_input("Credit / photographer")
            source_url = st.text_input("Source URL (required for public reference)")
        save = st.form_submit_button("Save observation", type="primary")
    if save:
        if source_video is None and photo is None:
            st.error("Choose a video or photo before saving.")
        else:
            try:
                if source_video is not None:
                    frame = frame_at(source_video, float(video_time))
                    media_key = POTHOLE_URL if public else file_sha256(source_video) if source_is_original else f"source-unavailable:{summary['source']}"
                else:
                    import cv2
                    import numpy as np
                    photo_bytes = photo.getvalue()
                    frame = cv2.imdecode(np.frombuffer(photo_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        raise ValueError("The photo could not be decoded")
                    media_key = hashlib.sha256(photo_bytes).hexdigest()
                evidence = marked_jpeg(frame, tuple(value / 100 for value in box))
                add_record(OBSERVATIONS, {
                    "category": category, "location": location.strip(), "description": description.strip(),
                    "precise_location": precise_location,
                    "source_kind": source_kind, "source_credit": source_credit.strip(), "source_url": source_url.strip(),
                    "media_date": media_date.strip(), "media_key": media_key,
                    "video_time_s": float(video_time) if video_time is not None else None,
                    "media_file": str(source_video.relative_to(HERE)) if source_video is not None and source_video.is_relative_to(HERE) else "",
                    "mark_box": [value / 100 for value in box],
                }, evidence, original_media=photo.getvalue() if photo is not None else None,
                   original_suffix=Path(photo.name).suffix if photo is not None else ".jpg")
                st.rerun()
            except (ValueError, OSError, RuntimeError) as error:
                st.error(f"Could not save observation: {error}")


def main() -> None:
    st.set_page_config(page_title="VISTA · Traffic Analytics", page_icon="🚦", layout="wide")
    st.title("VISTA")
    st.subheader("Vehicle Intelligence and Smart Traffic Analytics")
    st.write("Turn fixed-camera footage into reviewable vehicle crossing and visible-stop events.")
    st.caption("Python · YOLO26s primary model · YOLOv8n baseline · BoT-SORT · OpenCV · SQLite")

    section = st.sidebar.radio("Workspace", ["Traffic analysis", "Road observations"])
    if section == "Road observations":
        render_observations()
        return

    with st.sidebar:
        st.header("Saved runs")
        folders = saved_runs()
        options = [str(path) for path in folders]
        if options:
            preferred = RUNS / "colonel_by_yolo26s_final"
            active = st.session_state.get("active_run") or (str(preferred) if str(preferred) in options else None)
            selected = st.selectbox(
                "Open a run", options,
                index=options.index(active) if active in options else 0,
                format_func=lambda value: Path(value).name.replace("_", " "),
                key=f"saved_run_{active or 'initial'}",
            )
            st.session_state.active_run = selected
        else:
            selected = None
            st.caption("No completed runs yet.")
        st.divider()
        st.caption("Runs and uploaded clips are stored in the local `runs/` folder. On hosted Streamlit, uploads go to that server.")

    st.header("Analyze a traffic clip")
    source_choice = st.radio("Video source", ["Real signal clip (CC0)", "Overhead road clip", "Public road defect clip", "Synthetic stop demo", "Upload a video"], horizontal=True)
    uploaded_file = None
    if source_choice == "Upload a video":
        uploaded_file = st.file_uploader("Choose MP4, MOV or AVI", type=["mp4", "mov", "avi"])
        source = None
        if uploaded_file is not None:
            st.video(uploaded_file)
    elif source_choice == "Synthetic stop demo":
        source = STOP_SAMPLE
        st.caption("Synthetic test: a frame at 16.0s from the Intel clip is frozen for six seconds. This demonstrates the stop rule, not real traffic waiting time.")
        st.video(str(source))
    elif source_choice == "Overhead road clip":
        source = MOVING_SAMPLE
        st.caption("Intel IoT DevKit traffic clip · 30.16 seconds · CC BY 4.0. The sample demonstrates movement across a line.")
        st.video(str(source))
    elif source_choice == "Public road defect clip":
        source = POTHOLE_SAMPLE
        st.caption("Real road surface damage near Kumasi, Ghana · Amuzujoe / Wikimedia Commons · CC BY-SA 4.0. Its exact road is unknown. Crossings and stops on this crowded clip are unvalidated model outputs.")
        st.video(str(source))
    else:
        source = SIGNAL_SAMPLE
        st.caption("Real fixed-camera traffic signal · 20 seconds · Wikimedia Commons user 137a · CC0 1.0. Converted to 960 × 540 at 10 fps for this project.")
        st.video(str(source))

    signal_preset = source_choice == "Real signal clip (CC0)"
    pothole_preset = source_choice == "Public road defect clip"

    with st.expander("Camera line, zone and model settings", expanded=True):
        first, second, third = st.columns(3)
        with first:
            model_choice = st.selectbox("Detection model", list(MODELS))
            orientation = st.selectbox("Counting line", ["Horizontal", "Vertical"])
            line_percent = st.slider("Line position (%)", 5, 95, 60 if signal_preset else 65 if pothole_preset else 55, key=f"line_{source_choice}")
            confidence = st.slider(
                "Detection confidence", 0.05, 0.70,
                0.10 if source_choice == "Synthetic stop demo" else 0.25,
                0.05, key=f"confidence_{source_choice}",
            )
        with second:
            x_min = st.slider("Zone left (%)", 0, 90, 45 if signal_preset else 10 if pothole_preset else 2, key=f"zone_left_{source_choice}")
            x_max = st.slider("Zone right (%)", 10, 100, 100 if signal_preset else 72 if pothole_preset else 98, key=f"zone_right_{source_choice}")
            stop_seconds = st.slider("Visible stop after (s)", 0.5, 5.0, 2.0, 0.5)
        with third:
            y_min = st.slider("Zone top (%)", 0, 90, 45 if pothole_preset else 5, key=f"zone_top_{source_choice}")
            y_max = st.slider("Zone bottom (%)", 10, 100, 100 if signal_preset else 95 if pothole_preset else 94, key=f"zone_bottom_{source_choice}")
            stationary_speed = st.slider("Low motion (pixels/s)", 2.0, 20.0, 8.0, 1.0)
        frame_limit = st.number_input("Frame limit · 0 processes the whole clip", min_value=0, max_value=100000, value=0, step=100)

    if st.button("Analyze video", type="primary", disabled=source is None and uploaded_file is None):
        if x_min >= x_max or y_min >= y_max:
            st.error("The zone's right and bottom edges must be beyond its left and top edges.")
        else:
            config = RunConfig(
                line_axis="y" if orientation == "Horizontal" else "x",
                line_at=line_percent / 100,
                zone=(x_min / 100, y_min / 100, x_max / 100, y_max / 100),
                model=str(MODELS[model_choice]),
                confidence=confidence,
                stop_seconds=stop_seconds,
                max_stationary_speed_px_s=stationary_speed,
                max_frames=int(frame_limit) or None,
            )
            try:
                run_analysis(source or Path(uploaded_file.name), config, uploaded_file)
            except Exception as error:
                st.error(f"Analysis failed: {error}")

    if selected is not None:
        render_results(Path(selected))
    render_sample_comparison()
    st.caption("Signal clip: Wikimedia Commons user 137a, CC0 1.0. Overhead clip: Intel IoT DevKit, CC BY 4.0. Road defect clip: Amuzujoe, CC BY-SA 4.0. Validate model outputs for each new camera and scene.")


if __name__ == "__main__":
    main()
