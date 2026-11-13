"""Manual, evidence-backed road observations and standalone reports."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from decision_engine import observation_action


CATEGORIES = ("Pothole / broken surface", "Flooding", "Blocked lane", "Damaged sign or signal", "Other road issue")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame_at(video_path: Path, seconds: float):
    """Return a decoded frame at the selected timestamp, or raise a clear error."""
    import cv2

    if seconds < 0:
        raise ValueError("Video timestamp must be nonnegative")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else 0
        if duration > 0 and seconds >= duration:
            raise ValueError(f"Timestamp must be before {duration:.1f} seconds")
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok:
            raise ValueError(f"Cannot read a frame at {seconds:.2f} seconds")
        return frame
    finally:
        capture.release()


def marked_jpeg(frame, box: tuple[float, float, float, float]) -> bytes:
    """Create a full-frame evidence image with a reviewer-selected area marked."""
    import cv2

    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("Mark needs left < right and top < bottom")
    height, width = frame.shape[:2]
    image = frame.copy()
    cv2.rectangle(image, (round(x1 * width), round(y1 * height)),
                  (round(x2 * width), round(y2 * height)), (0, 210, 255), 3)
    cv2.rectangle(image, (0, 0), (min(width, 360), 35), (15, 32, 43), -1)
    cv2.putText(image, "Manual observation area", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise RuntimeError("Could not encode evidence image")
    return encoded.tobytes()


def load_records(folder: Path) -> list[dict]:
    path = folder / "records.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Observation store must contain a JSON list")
    return data


def add_record(
    folder: Path, details: dict, evidence_jpeg: bytes, *, record_id: str | None = None,
    original_media: bytes | None = None, original_suffix: str = ".jpg",
) -> dict:
    """Persist a reviewer-authored observation and its marked evidence frame."""
    for required in ("category", "location", "description", "source_kind", "media_key"):
        if not str(details.get(required, "")).strip():
            raise ValueError(f"Missing observation field: {required}")
    if details["category"] not in CATEGORIES:
        raise ValueError("Unsupported observation category")
    if details["source_kind"] == "Public reference" and not details.get("source_url"):
        raise ValueError("Public references need a source URL")
    if details.get("media_date"):
        try:
            date.fromisoformat(details["media_date"])
        except ValueError as error:
            raise ValueError("Media date must use YYYY-MM-DD") from error
    if not evidence_jpeg:
        raise ValueError("An evidence image is required")
    record_id = record_id or f"OBS-{uuid.uuid4().hex[:10].upper()}"
    if not record_id.replace("-", "").isalnum():
        raise ValueError("Invalid observation ID")
    folder.mkdir(parents=True, exist_ok=True)
    records = load_records(folder)
    if any(item["id"] == record_id for item in records):
        raise ValueError(f"Observation already exists: {record_id}")
    evidence = folder / "evidence" / f"{record_id}.jpg"
    evidence.parent.mkdir(exist_ok=True)
    evidence.write_bytes(evidence_jpeg)
    if original_media is not None:
        if original_suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise ValueError("Original photo must be JPG or PNG")
        original = folder / "media" / f"{record_id}{original_suffix.lower()}"
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(original_media)
        details = {**details, "original_media_file": f"media/{original.name}"}
    record = {
        "id": record_id,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence_file": f"evidence/{record_id}.jpg",
        **details,
    }
    records.append(record)
    destination = folder / "records.json"
    temporary = folder / "records.json.tmp"
    temporary.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, destination)
    return record


def pattern_for(record: dict, records: list[dict]) -> dict:
    """Find repeated reports at the *same entered* location and issue category."""
    location = " ".join(record["location"].casefold().split())
    related = [item for item in records if item["category"] == record["category"]
               and " ".join(item["location"].casefold().split()) == location]
    media = {item.get("media_key") for item in related if item.get("media_key")}
    dates = {item.get("media_date") for item in related if item.get("media_date")}
    precise_media = {item.get("media_key") for item in related if item.get("precise_location") and item.get("media_key")}
    precise_dates = {item.get("media_date") for item in related if item.get("precise_location") and item.get("media_date")}
    return {
        "observations": len(related),
        "distinct_media": len(media),
        "distinct_media_dates": len(dates),
        "recurrence_supported": bool(record.get("precise_location")) and len(precise_media) >= 2 and len(precise_dates) >= 2,
    }


def issue_counts(records: list[dict]) -> dict[str, int]:
    return dict(Counter(item["category"] for item in records))


def report_html(record: dict, records: list[dict], evidence_jpeg: bytes) -> str:
    """Make a portable, source-attributed report. It never claims official verification."""
    clean = lambda value: html.escape(str(value or ""))
    pattern = pattern_for(record, records)
    action = observation_action(record, pattern)
    recurrence = (
        f"{pattern['observations']} observations from {pattern['distinct_media']} separate media items "
        f"on {pattern['distinct_media_dates']} source dates. Recurrence is supported by these records only."
        if pattern["recurrence_supported"]
        else "One independent source/date is available here; a recurring pattern is not established."
    )
    url = str(record.get("source_url") or "")
    source_link = f'<a href="{clean(url)}">{clean(url)}</a>' if url.startswith(("http://", "https://")) else clean(url)
    image = base64.b64encode(evidence_jpeg).decode("ascii")
    time = record.get("video_time_s")
    video_time = f"{float(time):.2f} seconds" if time is not None else "Still photo"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{clean(record['id'])} · VISTA observation</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 24px;color:#172d35}}h1{{font-size:30px;margin-bottom:0}}.tag{{color:#396b78}}img{{width:100%;border-radius:8px}}dl{{display:grid;grid-template-columns:170px 1fr;gap:8px 16px}}dt{{font-weight:700}}dd{{margin:0}}.note{{background:#eef5f4;padding:16px;border-left:4px solid #168278}}footer{{font-size:13px;color:#52676e;margin-top:36px}}</style></head><body>
<p class="tag">VISTA · reviewer-authored road observation</p><h1>{clean(record['category'])}</h1><p>{clean(record['id'])}</p>
<img src="data:image/jpeg;base64,{image}" alt="Marked evidence frame"><p class="tag">Yellow rectangle was placed manually by the reviewer.</p>
<h2>Observation</h2><dl><dt>Location</dt><dd>{clean(record['location'])}</dd><dt>Media time</dt><dd>{clean(video_time)}</dd>
<dt>Source type</dt><dd>{clean(record['source_kind'])}</dd><dt>Media date</dt><dd>{clean(record.get('media_date', 'Unknown'))}</dd>
<dt>Site precision</dt><dd>{'Exact site declared by reporter' if record.get('precise_location') else 'Approximate or unknown'}</dd>
<dt>Reviewed</dt><dd>{clean(record['recorded_at_utc'])}</dd><dt>Source credit</dt><dd>{clean(record.get('source_credit', ''))}</dd>
<dt>Source link</dt><dd>{source_link}</dd></dl><p class="note">{clean(record['description'])}</p>
<h2>Pattern check</h2><p>{clean(recurrence)}</p>
<h2>Requested follow-up</h2><p class="note"><strong>{clean(action['title'])}</strong><br>{clean(action['next_step'])}</p><p>{clean(action['gate'])}</p>
<footer>This is a visual observation from the credited media, not an official inspection, geolocation verification, or proof that the road issue caused traffic delay. Record a second independently dated view before claiming recurrence. No report was sent to an authority by this software.</footer></body></html>"""
