"""Publish the Flask dashboard's saved evidence as a static Vercel viewer.

The local Python app remains the writable source of truth. This export contains
the same templates and recorded results, with server-only controls replaced by
clear links to the full local project.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "phase2_prototype"
WEB = ROOT / "vista-web"
PUBLIC = WEB / "public"
sys.path.insert(0, str(PYTHON))

from observations import load_records  # noqa: E402
from web_app import FINAL_RUNS, SOURCE_DATA, create_app  # noqa: E402


def clean_for_public(page: str) -> str:
    page = page.replace("LOCAL PYTHON MODEL", "PUBLIC EVIDENCE VIEWER")
    page = page.replace("Evidence stays on this machine.", "Saved results from the full Python project.")
    page = page.replace("SYSTEM READY", "PUBLIC VIEWER")
    page = page.replace("Local research prototype · Model results need scene-specific validation",
                        "Public evidence viewer · Saved Python results need scene-specific validation")
    page = re.sub(r'<form class="action-form".*?</form>',
                  '<span class="muted">Follow-up updates are saved in the local Python app.</span>',
                  page, flags=re.S)
    page = re.sub(r'<section id="validation".*?</section>',
                  '<section class="panel validation-card"><div class="panel-top"><div><span class="eyebrow">HUMAN CHECK</span>'
                  '<h2>Manual validation</h2></div></div><p class="muted" style="padding:0 24px 20px">'
                  'This published run is read only. Use the full Python project to add or import labels.</p></section>',
                  page, flags=re.S)
    page = page.replace('>New observation <span>↗</span></a>', '>Open local project <span>↗</span></a>')
    page = page.replace('>New analysis <span>↗</span></a>', '>Python analysis setup <span>↗</span></a>')
    page = page.replace('>Analyze a video <span aria-hidden="true">↗</span></a>',
                        '>Python analysis setup <span aria-hidden="true">↗</span></a>')
    return page


def main() -> None:
    app = create_app(PYTHON)
    app.testing = True
    client = app.test_client()
    routes: dict[str, str] = {
        "/": "/", "/analyze": "/analyze/", "/runs": "/runs/",
        "/actions": "/actions/", "/observations": "/observations/",
        "/observations/new": "/guide/", "/benchmark": "/benchmark/",
    }
    output_pages = {
        "/": PUBLIC / "index.html",
        "/analyze": PUBLIC / "analyze" / "index.html",
        "/runs": PUBLIC / "runs" / "index.html",
        "/actions": PUBLIC / "actions" / "index.html",
        "/observations": PUBLIC / "observations" / "index.html",
        "/benchmark": PUBLIC / "benchmark" / "index.html",
    }
    archive = PUBLIC / "archive"
    (PUBLIC / "static").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "static" / "app.js").unlink(missing_ok=True)
    for file in (PYTHON / "web_ui" / "static").iterdir():
        if file.is_file():
            shutil.copy2(file, PUBLIC / "static" / file.name)

    for run_id in sorted(FINAL_RUNS):
        folder = PYTHON / "runs" / run_id
        if not (folder / "summary.json").exists():
            continue
        route = f"/runs/{run_id}"
        routes[route] = route + "/"
        output_pages[route] = PUBLIC / "runs" / run_id / "index.html"
        target = archive / "runs" / run_id
        target.mkdir(parents=True, exist_ok=True)
        for file in folder.iterdir():
            if file.is_file():
                shutil.copy2(file, target / file.name)
        dashboard = target / "dashboard.html"
        if dashboard.exists():
            dashboard.write_text(re.sub(r'<input id="search"[^>]*>\s*', '',
                                        re.sub(r'<script>.*?</script>', '', dashboard.read_text(), flags=re.S)))
        import json
        summary = json.loads((folder / "summary.json").read_text())
        routes[f"{route}/video"] = f"/archive/runs/{run_id}/{Path(summary['video']).name}"
        for kind, filename in {
            "video": Path(summary["video"]).name, "events": "events.csv", "tracks": "tracks.csv",
            "json": "summary.json", "sqlite": "events.sqlite", "dashboard": "dashboard.html",
            "labels": "manual_labels.json",
        }.items():
            routes[f"{route}/download/{kind}"] = f"/archive/runs/{run_id}/{filename}"
        response = client.get(f"{route}/review-brief")
        if response.status_code != 200:
            raise RuntimeError(f"Could not export review brief for {run_id}: {response.status_code}")
        (target / "review-brief.html").write_bytes(response.data)
        routes[f"{route}/review-brief"] = f"/archive/runs/{run_id}/review-brief.html"

    records = load_records(PYTHON / "observations")
    for record in records:
        obs_id = record["id"]
        route = f"/observations/{obs_id}"
        routes[route] = route + "/"
        output_pages[route] = PUBLIC / "observations" / obs_id / "index.html"
        evidence = archive / "observations" / "evidence" / f"{obs_id}.jpg"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PYTHON / "observations" / record["evidence_file"], evidence)
        routes[f"{route}/evidence"] = f"/archive/observations/evidence/{obs_id}.jpg"
        report = archive / "observations" / "reports" / f"{obs_id}-report.html"
        report.parent.mkdir(parents=True, exist_ok=True)
        response = client.get(f"{route}/report")
        if response.status_code != 200:
            raise RuntimeError(f"Could not export observation report for {obs_id}: {response.status_code}")
        report.write_bytes(response.data)
        routes[f"{route}/report"] = f"/archive/observations/reports/{obs_id}-report.html"

    for key, (_, filename, _) in SOURCE_DATA.items():
        target = archive / "samples" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PYTHON / "sample_data" / filename, target)
        routes[f"/samples/{key}"] = f"/archive/samples/{filename}"

    def rewrite(match: re.Match[str]) -> str:
        prefix, original = match.groups()
        parts = urlsplit(original)
        destination = routes.get(parts.path, parts.path)
        return prefix + urlunsplit(("", "", destination, parts.query, parts.fragment)) + '"'

    for route, target in output_pages.items():
        response = client.get(route)
        if response.status_code != 200:
            raise RuntimeError(f"Could not export {route}: {response.status_code}")
        page = clean_for_public(response.get_data(as_text=True))
        if route == "/analyze":
            page = re.sub(r'<form id="analysis-form".*?</form>',
                          '<div class="panel form-panel"><span class="eyebrow">PYTHON ANALYSIS</span>'
                          '<h2>Run the model locally</h2><p>VISTA processes video with YOLO26s and BoT-SORT in Python. '
                          'The public site shows saved evidence; running a new clip needs the local Python app.</p>'
                          '<a class="button button-dark" href="https://github.com/JatinAggarwal5320/VISTA-vehicle-intelligence-traffic-analytics/tree/main/phase2_prototype">Open Python setup ↗</a></div>',
                          page, flags=re.S)
        page = re.sub(r'((?:href|src|poster)=")(/[^"]*)"', rewrite, page)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page)

    guide = PUBLIC / "guide" / "index.html"
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VISTA · Local project</title><link rel="stylesheet" href="/static/style.css"><main class="content" style="max-width:760px"><span class="eyebrow">LOCAL PYTHON PROJECT</span><h1>Create a road observation</h1><p>The public evidence viewer cannot save a new observation. Run the Python app from the GitHub project to upload a photo or video, mark a defect, and generate an evidence report.</p><a class="button button-dark" href="https://github.com/JatinAggarwal5320/VISTA-vehicle-intelligence-traffic-analytics/tree/main/phase2_prototype">Open Python setup ↗</a> <a class="text-link" href="/observations/">← Back to observations</a></main></html>''')
    print(f"Exported {len(output_pages)} dashboard pages and {len(records)} observation reports")


if __name__ == "__main__":
    main()
