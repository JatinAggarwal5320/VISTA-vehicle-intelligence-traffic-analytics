"""Export selected Python results as a static, source-attributed Vercel demo."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "phase2_prototype"
PUBLIC = ROOT / "vista-web" / "public" / "evidence"
sys.path.insert(0, str(PYTHON))

from decision_engine import observation_action, traffic_action, traffic_brief_html  # noqa: E402
from observations import load_records, pattern_for, report_html  # noqa: E402


SOURCES = {
    "cuttack_yolo26s": {
        "place": "Link Road, Cuttack, Odisha",
        "source_url": "https://commons.wikimedia.org/wiki/File:Moving_vehicles_in_Link_road,_Cuttack,_Odisha.webm",
        "credit": "Subhashish Panigrahi / Wikimedia Commons · CC BY-SA 3.0",
    },
    "bengaluru_night_yolo26s": {
        "place": "Ramana Maharshi Road, Bengaluru",
        "source_url": "https://commons.wikimedia.org/wiki/File:Ramana_Maharshi_Road,_Bangalore_(2025)_02.webm",
        "credit": "Gpkp / Wikimedia Commons · CC BY-SA 4.0",
    },
}


def frame_near(video: Path, seconds: float) -> bytes | None:
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            return None
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok:
            return None
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return encoded.tobytes() if ok else None
    finally:
        capture.release()


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    cards = []
    for run_id, source in SOURCES.items():
        folder = PYTHON / "runs" / run_id
        summary = json.loads((folder / "summary.json").read_text())
        action = traffic_action(run_id, summary, [], audited=False)
        video = folder / "annotated.mp4"
        shutil.copyfile(video, PUBLIC / f"{run_id}.mp4")
        frame = frame_near(video, (action["window_start"] or 0) + 2)
        (PUBLIC / f"{run_id}-review-brief.html").write_text(traffic_brief_html(action, summary, frame))
        cards.append({**action, **source, "media_type": "video", "media_url": f"/evidence/{run_id}.mp4",
                      "brief_url": f"/evidence/{run_id}-review-brief.html", "duration_s": summary["duration_s"]})

    records = load_records(PYTHON / "observations")
    record = next(item for item in records if item["id"] == "OBS-KOLKATA-001")
    action = observation_action(record, pattern_for(record, records))
    marked = (PYTHON / "observations" / record["evidence_file"]).read_bytes()
    (PUBLIC / "OBS-KOLKATA-001.jpg").write_bytes(marked)
    (PUBLIC / "OBS-KOLKATA-001-report.html").write_text(report_html(record, records, marked))
    cards.append({**action, "place": record["location"], "source_url": record["source_url"],
                  "credit": record["source_credit"], "media_type": "image",
                  "media_url": "/evidence/OBS-KOLKATA-001.jpg",
                  "brief_url": "/evidence/OBS-KOLKATA-001-report.html", "media_date": record["media_date"]})

    (PUBLIC / "index.json").write_text(json.dumps({
        "generated_from": "Saved Python YOLO26s / BoT-SORT results; action rules in phase2_prototype/decision_engine.py",
        "cards": cards,
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"Exported {len(cards)} evidence cards to {PUBLIC}")


if __name__ == "__main__":
    main()
