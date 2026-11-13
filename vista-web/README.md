# VISTA web app

A deployable public companion to the Python VISTA project. The top section presents **saved Python YOLO26s / BoT-SORT evidence** from Cuttack and Bengaluru, plus a reviewer-marked Kolkata road observation. Each card states a concrete next review or field step, links to the credited source, and opens a portable Python-generated brief/report. Follow-up status and notes are saved in that visitor's browser only.

Below those examples, the live analyzer runs **in the browser**: video frames are decoded locally, YOLOv8n detects cars, motorcycles, buses, and trucks, a lightweight tracker assigns IDs, and rule logic records directional line crossings and low-motion stop candidates. It now gives a five-second review target for each new result. This browser engine is separate from the Python model and benchmark.

## Run locally

Requires Node.js 20.19+ or 22.12+ (Vite 7 requirement) and a current desktop browser.

```bash
cd vista-web
npm ci
npm run dev
```

Open the URL printed by Vite, choose **Use included sample**, then **Analyze video**. This clip demonstrates directional crossings. **Try stop demo** loads a clearly marked synthetic six-second clip made by freezing a frame of the same source; it presets 10% confidence so the stop rule can be demonstrated. The first model load downloads about 26 MB of local app assets (ONNX model and WASM runtime); later loads may be cached. The included 30-second clip takes about 13 seconds at 2 analyzed frames per second on the development machine; hardware and chosen frame rate change this substantially.

For a production-style local run:

```bash
npm run build
npm run preview
```

## Deploy on Vercel

Import this repository into Vercel and set **Root Directory** to `vista-web`. Framework preset: **Vite**. Build command: `npm run build`. Output directory: `dist`. `vercel.json` supplies those settings; no environment variables or server database are needed. After deployment, confirm the three published evidence cards, then run the included sample to check browser inference.

This is a static app. The ONNX model, WASM runtime, sample clip, and selected Python evidence are included in `public/` and copied to `dist/` by Vite. Uploaded video and run history remain in the browser's IndexedDB, tied to that browser and origin. Follow-up status uses localStorage and is **not shared across reviewers**. Clearing browser data removes both. JSON and CSV exports let users retain new run results outside the browser. This design avoids sending a large video through a Vercel Function.

To refresh the published examples after Python results change, run `../.venv/bin/python scripts/build_public_evidence.py` from this folder. This copies the two annotated clips and Kolkata marked image, and rebuilds the JSON cards and portable briefs from `phase2_prototype/decision_engine.py`.

## What the app measures

- **Crossing:** a vehicle track's bottom-center moves from one side of the configurable counting line to the other. Each event has a timestamp, class, direction, track ID, and confidence.
- **Visible stop:** a vehicle track remains inside the drawn zone with low image motion for the configured duration. This is an image-based observation, **not** measured speed, queue delay, or a cause of congestion.
- **Manual evaluation:** users can label crossings and stops in the clip. A prediction matches a label when type and direction agree and timestamps are within ±1 second. Precision/recall are meaningful only after the entire clip is labeled.

The browser app uses the exported YOLOv8n model plus IoU/center-distance tracking. The [full Python project](../phase2_prototype/) uses YOLO26s plus **BoT-SORT**, and produces an annotated MP4, SQLite database, CSV, JSON, action queue, and standalone review briefs. These are two implementations with different models and trackers; their counts may differ. The Python project has a limited 11-event two-clip audit; the India scene outputs and live browser output have not been fully manually validated. The bundled browser sample is a moving-vehicle demonstration, not a signalized junction.

## Verification

```bash
npm test
npm run build
npm run preview
node scripts/smoke.mjs
```

The browser smoke script uses local Google Chrome and `http://127.0.0.1:4173/`. It checks sample analysis, event export, manual labeling, saving and reopening after reload, mobile horizontal overflow, and the synthetic stop demo. It currently expects 2 crossings across 61 sampled frames on the moving clip and 1 visible stop on the frozen clip, both at 2 FPS. These are regression expectations, not ground-truth traffic counts.

## Source and license notes

- Included `sample/traffic.mp4`: Intel IoT DevKit [`car-detection.mp4`](https://github.com/intel-iot-devkit/sample-videos), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The input clip is unchanged. `sample/stopped-demo.mp4` is a modified derivative: the frame at 15.5 seconds was frozen for six seconds for a synthetic test.
- `models/yolov8n.onnx`: exported from the Ultralytics pretrained `yolov8n.pt` checkpoint. Check [Ultralytics licensing](https://www.ultralytics.com/license) before redistribution or commercial reuse.
- `wasm/`: ONNX Runtime Web runtime files from the installed `onnxruntime-web` package.
- `evidence/`: selected Python outputs. The Cuttack clip derives from [Subhashish Panigrahi's video](https://commons.wikimedia.org/wiki/File:Moving_vehicles_in_Link_road,_Cuttack,_Odisha.webm), CC BY-SA 3.0; the Bengaluru clip derives from [Gpkp's video](https://commons.wikimedia.org/wiki/File:Ramana_Maharshi_Road,_Bangalore_(2025)_02.webm), CC BY-SA 4.0; the Kolkata image derives from [Sbb1413's photo](https://commons.wikimedia.org/wiki/File:Potholes_(1_November_2026).jpg), CC BY-SA 3.0. All are public references, not team-captured footage.
