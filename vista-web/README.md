# VISTA public evidence viewer

This folder is the Vercel companion to the [Python VISTA project](../phase2_prototype/). It serves a read-only export of the same Flask templates, saved runs, annotated video, benchmark, and road observations seen locally. Its aurora, glass, and responsive layouts use CSS. There is no JavaScript, Node build, or browser model.

## Run the model

Use the Python app for new video analysis, uploads, manual labels, and follow-up decisions:

```bash
cd phase2_prototype
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python web_app.py
```

Open `http://127.0.0.1:8501`. The model pipeline uses YOLO26s and BoT-SORT and saves its outputs to the local project. The [Python guide](../phase2_prototype/README.md) describes the sample data, settings, evaluation, and limits.

## Preview and deploy the public viewer

From `vista-web`, serve the generated `public` folder with Python:

```bash
python3 -m http.server 4173 --directory public
```

Open `http://127.0.0.1:4173`. On Vercel, import the repository with **Root Directory** `vista-web`. The checked-in `vercel.json` sets Framework to Other, disables the build command, and serves `public`. There are no environment variables.

After changing saved results or Flask templates, regenerate the viewer from the repository root:

```bash
python3 vista-web/scripts/export_flask_viewer.py
```

Commit and deploy the changed `public` files. The export contains the saved state at generation time; it cannot accept uploads or persist new follow-up decisions. For a writable shared deployment, the Python app needs a persistent Python host and storage.

## Evidence boundaries

The two-clip manual audit contains 11 reviewed line crossings. The saved YOLO26s runs matched 11/11; the YOLOv8n baseline matched 9/11 under a ±1 second event matching window. This small audit is not a general accuracy estimate. India scene event totals are not fully validated, and no signal-timing or road-delay claim is made from them. A separate synthetic frozen-frame clip checks the visible-stop rule.

The public Cuttack and Bengaluru videos and Kolkata road photo are credited in the app. They are not team-captured footage. The marked road issue is a field-check request; the exact location and current condition remain unverified.
