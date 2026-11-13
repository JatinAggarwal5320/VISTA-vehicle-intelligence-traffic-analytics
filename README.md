# VISTA — Vehicle Intelligence and Smart Traffic Analytics

VISTA is a Python-first computer-vision project that turns traffic footage and road observations into **reviewable follow-up actions**. It detects and tracks vehicles, records directional line crossings and visible-stop candidates, and saves annotated footage plus timestamped data. Its practical problem is deciding what a person should verify or inspect next, with the evidence kept attached.

## Run the Python project

    cd phase2_prototype
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python web_app.py

Open http://127.0.0.1:8501. The custom Flask dashboard is the main interface; the model, tracking, evaluation, and reporting stay in Python. It includes a saved signal analysis, an overhead clip, two real India traffic scenes, and a public road-defect clip. You can run a sample or upload a video, inspect events, and export MP4, CSV, JSON, SQLite, or per-frame tracks. YOLO26s is the primary detector; YOLOv8n is the measured baseline. See the [Python project guide](phase2_prototype/README.md) for settings, dataset sources, evaluation, and limits.

The **Action center** is the evidence-to-decision layer. It selects a five-second window for manual traffic-event review, exposes a downloadable review brief, and tracks Open/In review/Referred/Closed states with notes. The **Road observations** section lets a reviewer mark an issue, preserve its source and date, and download an evidence-backed report with a specific field-check request. It includes a [public pothole photo from Kolkata](https://commons.wikimedia.org/wiki/File:Potholes_(1_November_2026).jpg) and a [public road-defect video from Kumasi](https://commons.wikimedia.org/wiki/File:Cars_Moving_into_pothole.webm). Neither was team captured. Their exact present road conditions are unverified. A recurring-issue claim requires separate dated media at a precise location.

Across **two real clips and 11 manually reviewed line crossings**, the saved YOLO26s runs matched 11/11; the YOLOv8n baseline matched 9/11. Event matching allows ±1 second and checks direction and class. This is a small single-reviewer audit, not a general accuracy claim. The real clips have no validated waiting events; a separately marked synthetic frozen-frame clip checks the stop rule.

The [Vercel site](vista-web/README.md) now displays a read-only export of the **same Flask dashboard design and saved Python evidence** as the local app. Its separate browser analyzer runs YOLOv8n/IoU in the visitor's browser, so live browser counts remain separate from the Python benchmark. The full Flask app still needs a persistent Python host for uploads, background processing, and shared follow-up status; the Vercel viewer does not run that pipeline. The previous Streamlit UI remains optional in app.py.

The [review presentation](output/VISTA_Minor_Project_Proposal.pptx) covers background, literature, limitations, plan, methodology, architecture, and references.
