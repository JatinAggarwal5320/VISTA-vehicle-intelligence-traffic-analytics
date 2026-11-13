# VISTA · Python traffic analytics project

VISTA turns fixed-camera footage and manually marked road issues into **specific inspection tasks with evidence attached**. It detects cars, motorcycles, buses, and trucks with Ultralytics YOLO, keeps IDs across frames with BoT-SORT, counts line crossings, and marks vehicles that remain nearly stationary in a chosen image zone. The server and analysis pipeline are Python; the custom interface uses HTML and CSS. The analysis form posts directly to Flask and waits for the Python result.

This is a working minor project with two manually audited **real** traffic clips, two India scene tests, a public road-defect clip, pretrained model checkpoints, saved outputs, crossing labels, and a reproducible comparison. It does not train a new detector or control a signal.

## Start the app

From this folder, with Python 3.10 or newer:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python web_app.py

Open http://127.0.0.1:8501. The custom dashboard is served by Flask; model and data logic stay in Python. Choose the real signal clip, overhead road clip, Cuttack daytime junction view, Bengaluru night traffic, public road-defect clip, synthetic stop test, or upload a fixed-camera MP4/MOV/AVI/WEBM. Set a counting line and stop zone, then select **Run analysis**. The page shows progress and opens the completed run. Both model checkpoints are bundled. CPU inference may take longer for larger clips.

The old Streamlit UI is optional: install requirements_streamlit.txt and run streamlit run app.py. It uses the same pipeline and saved data. The Flask interface is the main project application.

The overview opens a saved real signal run immediately. Each new run writes annotated.mp4, tracks.csv, events.csv, events.sqlite, summary.json, and dashboard.html under runs/. You can inspect and download these files, enter or import manual labels, and compare events against them.

## The decision this project supports

**Problem:** A junction camera may record hundreds of frames, but a reviewer still has to decide *which event to inspect, whether a count is trustworthy, and what follow-up to request*. Raw detection totals do not answer those questions. Road-defect photos often lose their source, date, or exact status before anyone can inspect them.

Open **Action center** after an analysis. VISTA groups crossing candidates into five-second windows and identifies the densest window as a **manual review target**, not a traffic peak. The run page also exports a portable HTML review brief with a representative frame and the candidate event timestamps/track IDs. A reviewer checks the footage, adds or corrects labels, then records the action as Open, In review, Referred, or Closed with a note. The status is saved locally in `actions/status.json`. Marking Referred or Closed requires a note; no message is sent by the app.

For a marked road issue, the action is to locate and verify the defect on site. The included [Kolkata public photo](https://commons.wikimedia.org/wiki/File:Potholes_(1_November_2026).jpg) provides camera coordinates, so the review task identifies an area to search, while clearly stating that the exact defect point and present condition are unverified. The downloadable observation report now includes the requested follow-up. If separate dated media from the same precise location support recurrence, the action changes to request a site inspection/referral. This is a **decision-support and evidence handoff** contribution, not an automatic signal controller.

**Demonstration:** Open the saved Cuttack run, inspect its suggested five-second window, download the review brief, and mark the task In review. Open the Kolkata observation, inspect the marked photo and source, download its report, and record the field-check outcome in Action center. The Cuttack count and stop candidates are unvalidated; the Kolkata source is public, not a team field report.

**Boundary:** The included traffic clips last 20–30 seconds. They cannot establish a recurring peak, congestion cause, emissions savings, or a safe signal timing. A signal recommendation would require validated, longer recordings from the same site at comparable times on different dates, plus a traffic engineer's assessment. VISTA currently routes the evidence to that next investigation rather than pretending it has those data.

## Road observations and issue reports

Open **Road observations** in the sidebar. VISTA includes a public road-defect photo from Kolkata and a 20.7-second public road-defect video from Kumasi, each with a reviewer-marked example. Neither was captured by the team. The Kolkata photo lists a camera point but not a verified defect point; the Kumasi source does not identify an exact road or junction. Standalone reports are under `observations/reports/`.

To create an observation from your own footage, analyze/upload the video on **Analyze footage**, then choose **Saved VISTA run** under **Road observations**. You can also upload a photo. Enter the actual location, source/date, a factual description, the frame timestamp, and a manually selected rectangle. VISTA saves the marked evidence frame, original uploaded photo where applicable, and metadata. The report is a downloadable standalone HTML file with the image embedded. It is not automatically sent to anyone.

The **pattern check** groups observations by the same entered location and issue category. It requires at least two distinct media items on two source dates and a precise location before indicating recurrence. One clip cannot establish a recurring pothole or show that the defect caused congestion. This issue-report workflow is manual review; YOLO is used for vehicles, not pothole detection. An analyzed run of the crowded Kumasi clip is included for context, but its 10 crossing and one stop **model outputs have no manual traffic-event labels and are not accuracy results**.

The [Cuttack](https://commons.wikimedia.org/wiki/File:Moving_vehicles_in_Link_road,_Cuttack,_Odisha.webm) and [Bengaluru](https://commons.wikimedia.org/wiki/File:Ramana_Maharshi_Road,_Bangalore_(2025)_02.webm) samples show real traffic in India from fixed viewpoints. Their included saved runs are scene tests; they have no complete manual crossing/stop labels and are excluded from the benchmark. See [sample source details](sample_data/SOURCES.md) for creator credit, licenses, dates, and conversions.

## Command line

Run from this folder so model paths resolve:

    .venv/bin/python run.py sample_data/colonel_by_signal_10fps.mp4 \
      --output runs/my_signal --axis y --line 0.60 \
      --zone 0.45,0.05,1.00,1.00

For the overhead clip, use sample_data/intel_car_detection.mp4, --line 0.55, and --zone 0.02,0.05,0.98,0.94. Use --model yolov8n.pt for the baseline. --axis x gives a vertical counting line; --axis y gives a horizontal one. Coordinates are fractions of the frame. Use --max-frames 100 for a quick smoke test and --device cpu to force CPU inference.

Rebuild the saved benchmark and run tests:

    .venv/bin/python benchmark.py
    .venv/bin/python -m unittest discover -v

benchmark.py reads the manual CSVs and four saved model summaries, recalculates event matching, and writes evaluation_data/benchmark_results.json. To compare a new run with complete manual labels:

    .venv/bin/python evaluate_run.py --labels evaluation_data/colonel_by_crossings.csv \
      runs/my_signal/summary.json

## Measured results on included clips

All comparisons use the same BoT-SORT tracker and scene settings. A predicted crossing matches one manual crossing of the same direction and class within ±1 second. The manual timestamps were estimated from visual review of original video, independent of the model boxes. See evaluation_data/README.md and evaluation_data/colonel_by_audit.md for actual intervals and audit limits.

| Real clip | Manual crossings | YOLOv8n baseline | YOLO26s primary |
| --- | ---: | ---: | ---: |
| Overhead road, 30.16 s | 4 | 2 matched, 2 missed | 4 matched, 0 missed |
| Fixed traffic signal, 20 s | 7 | 7 matched, 0 missed | 7 matched, 0 missed |
| Both clips | 11 | 9/11 recall, 100% precision | 11/11 recall, 100% precision |

On this machine, YOLO26s took 25.84 seconds to process both clips versus 15.74 seconds for YOLOv8n. The 100% precision figure means **no extra events among these 11 audited crossings**, not perfect detection accuracy. Two short clips with one reviewer cannot establish performance on other cameras, weather, lighting, vehicle classes, or congestion levels. A second team member should check the labels before formal reporting.

The real clips yielded **zero verified visible-stop events**. sample_data/stopped_demo.mp4 freezes one Intel frame for six seconds and produces one stop event. This checks the stop rule, not real queue or waiting-time accuracy. The system does not infer actual speed, delay, emissions, or signal timing.

## Use your own traffic video or UA-DETRAC

For a new camera, choose a line that crosses a travel path. Watch the original footage and label **every** crossing at that line before reporting recall. Check whether a vehicle keeps one track ID while crossing. Choose a stop zone where whole vehicles remain visible, then label complete stopped intervals if evaluating stops.

[UA-DETRAC's official page](https://sites.google.com/view/daweidu/projects/ua-detrac) provides annotated fixed-camera image sequences. The large image archive is not bundled. After downloading and extracting one sequence and matching XML:

    .venv/bin/python prepare_ua_detrac.py \
      --images /path/to/DETRAC-Train-Images/MVI_20011 \
      --xml /path/to/DETRAC-Train-Annotations-XML/MVI_20011.xml \
      --output sample_data/ua_detrac_mvi_20011 --frames 750 --axis y --line 0.55

Adjust paths and line orientation. The importer derives crossing labels from the provided boxes and IDs; visually review the generated line and labels before reporting a benchmark.

## Sources, credit, and limits

- sample_data/colonel_by_signal_original.webm: [Temporary traffic signal at Colonel By Drive](https://commons.wikimedia.org/wiki/File:Temporary_traffic_signal_at_Colonel_By_Drive.webm), Wikimedia Commons user 137a, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). colonel_by_signal_10fps.mp4 is a downscaled, 10 fps, audio-free conversion.
- sample_data/intel_car_detection.mp4: car-detection.mp4 from [Intel IoT DevKit sample-videos](https://github.com/intel-iot-devkit/sample-videos), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). stopped_demo.mp4 is a marked synthetic frozen-frame derivative.
- sample_data/kumasi_pothole_10fps.mp4: downsampled, audio-free derivative of [Cars Moving into pothole](https://commons.wikimedia.org/wiki/File:Cars_Moving_into_pothole.webm), by Amuzujoe, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The original source describes a road near Kumasi, Ghana; precise coordinates are not provided. The video derivative and marked evidence retain that attribution and license.
- sample_data/cuttack_link_road_30s.mp4: 40–70-second segment of [Link Road, Cuttack, Odisha](https://commons.wikimedia.org/wiki/File:Moving_vehicles_in_Link_road,_Cuttack,_Odisha.webm), by Subhashish Panigrahi, [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/), converted to 960×540 at 10 fps without audio.
- sample_data/bengaluru_night_20s.mp4: 20-second derivative of [Ramana Maharshi Road, Bangalore (2025) 02](https://commons.wikimedia.org/wiki/File:Ramana_Maharshi_Road,_Bangalore_(2025)_02.webm), by Gpkp, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), converted to 10 fps without audio.
- observations/media/OBS-KOLKATA-001.jpg: 1280-pixel copy of [Potholes (1 November 2026)](https://commons.wikimedia.org/wiki/File:Potholes_(1_November_2026).jpg), by Sbb1413, [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). The marked evidence is a derivative. The source camera coordinates are an approximate inspection lead, not a verified pothole location.
- yolo26s.pt and yolov8n.pt are pretrained Ultralytics weights. Check [Ultralytics licensing](https://www.ultralytics.com/license) for use beyond this academic project.

Saved outputs show exact source, model, tracker, settings, timestamps, and track IDs. tracks.csv is the frame-level record. New runs can vary across package versions or hardware, so the included summaries are measured reference outputs.

## Code map

- web_app.py and web_ui/: primary Flask dashboard, upload and job progress, run review, benchmark, and observation forms.
- app.py: optional earlier Streamlit interface.
- video_pipeline.py: frame decoding, YOLO + BoT-SORT, overlays, data export.
- vista_events.py: crossing and image-space stop rules.
- evaluation.py, evaluate_run.py, benchmark.py: matching and result reports.
- prepare_ua_detrac.py: optional annotated dataset import.
- observations.py: manual issue evidence, provenance, recurrence check, and HTML report.
- decision_engine.py: deterministic next-action rules, review brief, and local follow-up status.
- dashboard.py: standalone HTML run report.
- test_*.py: rule, evaluation, and parser tests.
