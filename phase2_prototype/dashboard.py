"""Create a self-contained, readable report for a processed VISTA clip."""

from __future__ import annotations

import html
import json
from pathlib import Path


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _chart(events: list[dict], duration_s: float) -> str:
    buckets = max(1, min(12, int(duration_s // 5) + 1))
    width = 840
    height = 190
    plot_bottom = 155
    counts = [0] * buckets
    for event in events:
        if event["type"] == "crossing":
            index = min(buckets - 1, int(event["time_s"] / max(duration_s, 0.01) * buckets))
            counts[index] += 1
    peak = max(1, max(counts))
    bar_step = (width - 40) / buckets
    bars = []
    for index, count in enumerate(counts):
        x = 20 + index * bar_step + 10
        bar_width = max(12, bar_step - 20)
        bar_height = count / peak * 112
        y = plot_bottom - bar_height
        label = f"{index * duration_s / buckets:.0f}s"
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="4" fill="#06889a"/>'
            f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="bar-value">{count}</text>'
            f'<text x="{x + bar_width / 2:.1f}" y="177" text-anchor="middle" class="axis-label">{label}</text>'
        )
    return f'<svg role="img" aria-label="Crossings over video time" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet"><line x1="20" y1="155" x2="820" y2="155" stroke="#c8d4da"/>{"".join(bars)}</svg>'


def write_dashboard(summary: dict, path: Path) -> None:
    events = summary["events"]
    rows = []
    for event in events:
        detail = event.get("direction") or f'{event.get("duration_s", 0):.1f}s visible stop'
        text = " ".join(str(event.get(key, "")) for key in ("type", "vehicle_class", "track_id", "direction"))
        rows.append(
            f'<tr data-search="{_esc(text.lower())}"><td>{event["time_s"]:.1f}s</td>'
            f'<td><span class="tag {_esc(event["type"])}">{_esc(event["type"])}</span></td>'
            f'<td>{_esc(event["vehicle_class"])}</td><td>#{event["track_id"]}</td><td>{_esc(detail)}</td></tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="5" class="empty">No line crossings or visible stops were recorded in this clip with these settings.</td></tr>')
    direction_cards = "".join(
        f'<div><span>{_esc(direction.replace("_", " "))}</span><strong>{count}</strong></div>'
        for direction, count in sorted(summary["by_direction"].items())
    ) or '<div><span>No crossing direction recorded</span><strong>0</strong></div>'
    config = summary["config"]
    line_description = ("vertical" if config["line_axis"] == "x" else "horizontal") + f' at {config["line_at"]:.0%}'
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VISTA · {_esc(summary['source'])}</title>
<style>
:root{{--ink:#132b38;--muted:#607480;--teal:#06889a;--line:#dbe4e8;--paper:#f5f8f9;--white:#fff}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,Arial,sans-serif}}
.shell{{max-width:1200px;margin:auto;padding:32px 28px 64px}}.top{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:16px}}
.brand{{font-weight:850;letter-spacing:.12em;color:var(--teal);font-size:19px}}.eyebrow{{text-transform:uppercase;letter-spacing:.12em;color:var(--teal);font-weight:700;font-size:12px}}
h1{{font-size:clamp(32px,4vw,52px);letter-spacing:-.035em;margin:24px 0 8px}}p{{line-height:1.6}}.muted{{color:var(--muted)}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}}.stat,.panel{{background:var(--white);border:1px solid var(--line);border-radius:12px}}
.stat{{padding:22px}}.stat span{{display:block;color:var(--muted);font-size:14px}}.stat strong{{display:block;font-size:38px;margin-top:8px;letter-spacing:-.03em}}
.grid{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:20px}}.panel{{padding:22px;margin-bottom:20px}}h2{{font-size:19px;margin:0 0 18px}}
video{{width:100%;aspect-ratio:{summary['width']}/{summary['height']};background:#11232d;border-radius:7px}}.downloads{{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}}
a.button{{display:inline-block;padding:9px 13px;border:1px solid var(--line);border-radius:7px;text-decoration:none;color:var(--ink);font-size:13px;font-weight:650}}a.button:hover{{border-color:var(--teal);color:var(--teal)}}
.directions>div{{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:12px 0}}.directions strong{{font-size:18px}}.directions span{{text-transform:capitalize;color:var(--muted)}}
dl{{display:grid;grid-template-columns:130px 1fr;gap:10px 14px;font-size:14px}}dt{{color:var(--muted)}}dd{{margin:0;font-weight:600;overflow-wrap:anywhere}}
svg{{width:100%;height:auto}}.bar-value{{fill:var(--ink);font-size:13px;font-weight:700}}.axis-label{{fill:var(--muted);font-size:11px}}
input{{width:100%;max-width:320px;padding:10px 12px;border:1px solid var(--line);border-radius:7px;font:inherit;margin:0 0 14px}}
table{{width:100%;border-collapse:collapse;text-align:left;font-size:14px}}th,td{{padding:12px 8px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.07em}}
.tag{{display:inline-block;padding:4px 8px;border-radius:4px;background:#e0f2f2;color:#067181;font-weight:700;text-transform:capitalize}}.tag.stop{{background:#fff0d8;color:#9d5d09}}.empty{{color:var(--muted);text-align:center;padding:32px}}
.note{{border-left:3px solid var(--teal);padding-left:14px;color:var(--muted);font-size:14px}}@media(max-width:760px){{.stats,.grid{{grid-template-columns:1fr}}.shell{{padding:20px}}table{{font-size:12px}}}}
</style></head><body><main class="shell">
<header class="top"><div class="brand">VISTA</div><div class="muted">Vehicle Intelligence & Smart Traffic Analytics</div></header>
<div class="eyebrow" style="margin-top:28px">Video analysis · prototype report</div>
<h1>Traffic, made inspectable.</h1><p class="muted">{_esc(summary['source'])} · {summary['duration_s']:.1f}s analyzed · {summary['width']} × {summary['height']} px</p>
<section class="stats"><div class="stat"><span>Directional crossings</span><strong>{summary['crossings']}</strong></div>
<div class="stat"><span>Visible stop events</span><strong>{summary['stops']}</strong></div>
<div class="stat"><span>Frames processed</span><strong>{summary['frames']}</strong></div></section>
<div class="grid"><div>
<section class="panel"><h2>Annotated footage</h2><video controls preload="metadata" src="{_esc(summary['video'])}"></video>
<div class="downloads"><a class="button" href="{_esc(summary['video'])}" download>Download video</a><a class="button" href="events.csv" download>Download events CSV</a><a class="button" href="summary.json" download>Download JSON</a></div></section>
<section class="panel"><h2>Crossings over time</h2>{_chart(events, summary['duration_s'])}</section></div>
<aside><section class="panel"><h2>Direction counts</h2><div class="directions">{direction_cards}</div></section>
<section class="panel"><h2>Run setup</h2><dl><dt>Detector</dt><dd>{_esc(summary['model'])}</dd><dt>Tracker</dt><dd>{_esc(summary['tracker'])}</dd>
<dt>Counting line</dt><dd>{_esc(line_description)}</dd><dt>Stop zone</dt><dd>{_esc(config['zone'])}</dd><dt>Stop rule</dt><dd>≥ {config['stop_seconds']}s, ≤ {config['max_stationary_speed_px_s']} px/s</dd></dl></section>
<section class="panel"><h2>What this measures</h2><p class="note">Events come from tracked boxes in this camera view. A visible stop is a stationary-track proxy inside the marked zone. It does not measure physical queue length, road speed, delay, or the reason a vehicle stopped.</p></section></aside></div>
<section class="panel"><h2>Event log</h2><input id="search" type="search" placeholder="Filter by type, class, direction or track ID" aria-label="Filter events">
<table><thead><tr><th>Video time</th><th>Event</th><th>Class</th><th>Track</th><th>Detail</th></tr></thead><tbody id="eventRows">{''.join(rows)}</tbody></table></section>
<p class="muted" style="font-size:12px">Prototype output. Check detections and event counts against manually labelled footage before reporting accuracy.</p>
</main><script>document.getElementById('search').addEventListener('input',function(){{const query=this.value.toLowerCase().trim();document.querySelectorAll('#eventRows tr[data-search]').forEach(row=>{{row.hidden=!row.dataset.search.includes(query)}})}})</script></body></html>"""
    path.write_text(page, encoding="utf-8")
