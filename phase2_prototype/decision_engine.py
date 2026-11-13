"""Turn saved evidence into bounded, reviewable next actions.

These rules organize human work. They do not infer causes, signal timings, or
road safety from a short video.
"""

from __future__ import annotations

import json
import os
import base64
import html
from pathlib import Path


STATUSES = ("open", "in_review", "referred", "closed")


def traffic_action(run_id: str, summary: dict, labels: list[dict], *, audited: bool = False) -> dict:
    duration = max(0.0, float(summary.get("duration_s", 0)))
    crossings = [event for event in summary.get("events", []) if event.get("type") == "crossing"]
    stops = [event for event in summary.get("events", []) if event.get("type") == "stop"]
    buckets: dict[int, int] = {}
    for event in crossings:
        start = int(float(event["time_s"]) // 5) * 5
        buckets[start] = buckets.get(start, 0) + 1
    busiest = sorted(buckets.items(), key=lambda item: (-item[1], item[0]))[0] if buckets else None
    if busiest:
        start, count = busiest
        window = f"{start:g}–{min(start + 5, duration):g}s"
        evidence = f"{count} model crossing candidate{'s' if count != 1 else ''} in video time {window}; {len(crossings)} in {duration:g}s overall."
    else:
        start, count = 0, 0
        window = None
        evidence = f"No line crossing candidates in {duration:g}s of footage."

    if not crossings:
        title = "Check the counting line and camera view"
        next_step = "Watch the clip and confirm whether vehicles actually cross the chosen line. Move the line and rerun if it misses their paths."
    elif not audited:
        title = f"Verify crossings at {window}"
        next_step = "Review this video window against the original footage. Correct track-ID switches and add manual labels before using the count."
    else:
        title = "Collect a repeat recording at this site"
        next_step = "The included clip has manual crossing labels. Record independent, dated footage from the same camera during comparable periods before claiming a recurring flow pattern."

    if stops and not any(label.get("type") == "stop" for label in labels):
        stop_note = f" {len(stops)} low-motion stop candidate(s) also need manual review; they are not measured queue delay."
    else:
        stop_note = ""
    return {
        "id": f"run:{run_id}", "kind": "traffic", "source_id": run_id,
        "title": title, "evidence": evidence, "next_step": next_step + stop_note,
        "gate": "No signal-timing or congestion recommendation: this clip is under two minutes and has no comparable repeat recording."
        if duration < 120 else "Validate this camera's events and compare independent dated recordings before recommending an operational change.",
        "window_start": start if busiest else None,
        "window_label": window,
        "audited": audited,
    }


def observation_action(record: dict, pattern: dict) -> dict:
    if record.get("camera_lat") is not None and record.get("camera_lon") is not None:
        site = f"near source camera {record['camera_lat']:.6f}, {record['camera_lon']:.6f}"
    else:
        site = f"at the reported area: {record['location']}"
    if pattern["recurrence_supported"]:
        title = "Refer repeated road issue for site inspection"
        next_step = f"Send this evidence to the appropriate road maintainer and request an on-site inspection {site}. Log the referral and eventual field finding."
        gate = "Repeated source evidence supports follow-up, but road condition and precise position still need field verification."
    else:
        title = "Locate and verify this road issue"
        next_step = f"Arrange an on-site check {site}. Confirm the exact defect point and whether it is still present; capture a new dated view."
        gate = "One source is an inspection lead, not a verified recurring defect or proof of traffic impact."
    return {
        "id": f"observation:{record['id']}", "kind": "observation", "source_id": record["id"],
        "title": title, "evidence": record["description"], "next_step": next_step,
        "gate": gate, "window_start": record.get("video_time_s"), "window_label": None,
        "audited": False,
    }


def traffic_brief_html(action: dict, summary: dict, frame_jpeg: bytes | None) -> str:
    """Portable review request; a representative frame is evidence, not a verdict."""
    clean = lambda value: html.escape(str(value or ""))
    frame = (f'<img src="data:image/jpeg;base64,{base64.b64encode(frame_jpeg).decode()}" '
             f'alt="Frame near proposed review window">') if frame_jpeg else "<p>Frame preview unavailable.</p>"
    events = [event for event in summary.get("events", []) if event.get("type") == "crossing"]
    if action["window_start"] is not None:
        events = [event for event in events if action["window_start"] <= float(event["time_s"]) < action["window_start"] + 5]
    rows = "".join(
        f"<tr><td>{float(event['time_s']):.2f}s</td><td>{clean(event.get('vehicle_class'))}</td>"
        f"<td>#{clean(event.get('track_id'))}</td><td>{clean(event.get('direction', '').replace('_', ' '))}</td></tr>"
        for event in events
    ) or '<tr><td colspan="4">No crossing candidates in this window.</td></tr>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>VISTA review brief · {clean(action['source_id'])}</title>
<style>body{{font:15px/1.55 system-ui,sans-serif;max-width:850px;margin:40px auto;padding:0 24px;color:#172f32}}h1{{font-size:32px;line-height:1.1}}.tag{{font-size:11px;letter-spacing:.14em;color:#247d70;font-weight:800}}img{{max-width:100%;border-radius:8px}}section{{border-top:1px solid #dce5dd;padding:18px 0}}.callout{{background:#ecf4ee;padding:16px;border-left:4px solid #247d70}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid #e1e8e2;text-align:left}}footer{{font-size:12px;color:#63776d;margin-top:30px}}</style></head><body>
<p class="tag">VISTA / TRAFFIC REVIEW REQUEST</p><h1>{clean(action['title'])}</h1><p>Run {clean(action['source_id'])} · {clean(summary.get('source'))} · {float(summary.get('duration_s', 0)):g}s source clip</p>
<section><h2>Why review this?</h2><p>{clean(action['evidence'])}</p><div class="callout"><strong>Next step</strong><p>{clean(action['next_step'])}</p></div></section>
<section><h2>Frame near review window</h2>{frame}<p>Inspect the full annotated video and original footage before validating a count.</p></section>
<section><h2>Crossing candidates in window</h2><table><tr><th>Video time</th><th>Class</th><th>Track</th><th>Direction</th></tr>{rows}</table></section>
<footer>{clean(action['gate'])} This brief is generated from model results; it is not a traffic engineering recommendation. No task or report has been sent outside VISTA.</footer></body></html>"""


def load_statuses(folder: Path) -> dict[str, dict]:
    path = folder / "status.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Action status store must contain a JSON object")
    return data


def save_status(folder: Path, action_id: str, status: str, note: str, updated_at: str) -> None:
    if status not in STATUSES:
        raise ValueError("Invalid action status")
    if len(note) > 500:
        raise ValueError("Action note is too long")
    folder.mkdir(parents=True, exist_ok=True)
    data = load_statuses(folder)
    data[action_id] = {"status": status, "note": note.strip(), "updated_at": updated_at}
    temporary = folder / "status.json.tmp"
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, folder / "status.json")
