import io
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from observations import load_records
from web_app import HERE, create_app


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        (self.data / "sample_data").mkdir()
        shutil.copyfile(HERE / "sample_data" / "colonel_by_signal_10fps.mp4",
                        self.data / "sample_data" / "colonel_by_signal_10fps.mp4")
        self.calls = []

        def fake_process(source, folder, config, progress):
            self.calls.append((source, folder, config))
            progress(2, 2)
            shutil.copyfile(source, folder / "annotated.mp4")
            (folder / "summary.json").write_text(json.dumps({
                "source": source.name, "model": config.model, "tracker": config.tracker,
                "duration_s": .2, "frames": 2, "fps": 10, "width": 960, "height": 540,
                "crossings": 0, "stops": 0, "events": [], "by_direction": {},
                "video": "annotated.mp4", "config": {"line_axis": config.line_axis},
                "processing_s": .01,
            }))

        self.app = create_app(self.data, process_fn=fake_process)
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_all_primary_pages_render_from_project_data(self):
        actual = create_app()
        actual.testing = True
        client = actual.test_client()
        for route in ("/", "/analyze", "/runs", "/benchmark", "/observations",
                      "/actions", "/observations/OBS-KUMASI-001", "/observations/OBS-KOLKATA-001", "/runs/cuttack_yolo26s"):
            with self.subTest(route=route):
                self.assertEqual(client.get(route).status_code, 200)

    def test_analysis_job_uses_python_pipeline_and_reports_progress(self):
        started = self.client.post("/api/jobs", data={"source": "signal", "model": "yolo26s", "max_frames": "2"})
        self.assertEqual(started.status_code, 202)
        job_id = started.json["job_id"]
        for _ in range(100):
            status = self.client.get(f"/api/jobs/{job_id}").json
            if status["status"] in ("complete", "error"):
                break
            time.sleep(.01)
        self.assertEqual(status["status"], "complete")
        self.assertEqual((status["done"], status["total"]), (2, 2))
        self.assertEqual(self.calls[0][2].max_frames, 2)
        self.assertEqual(self.client.get(status["result_url"]).status_code, 200)
        self.assertEqual(self.client.get(f"{status['result_url']}/review-brief").status_code, 200)
        action_page = self.client.get("/actions")
        self.assertIn(status["run_id"].encode(), action_page.data)
        update = self.client.post(f"/actions/run/{status['run_id']}/status", data={"status": "in_review", "note": "Checked source"})
        self.assertEqual(update.status_code, 302)
        self.assertEqual(json.loads((self.data / "actions" / "status.json").read_text())[f"run:{status['run_id']}"]["status"], "in_review")
        rejected = self.client.post(f"/actions/run/{status['run_id']}/status", data={"status": "referred", "note": ""})
        self.assertIn("error=", rejected.headers["Location"])

    def test_invalid_analysis_settings_rejected(self):
        response = self.client.post("/api/jobs", data={"source": "signal", "line_at": "1.4"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.data / "runs").exists() and any((self.data / "runs").iterdir()))

    def test_python_form_processes_sample_without_javascript(self):
        page = self.client.get("/analyze")
        self.assertIn(b'action="/analyze/run"', page.data)
        self.assertNotIn(b'<script', page.data)
        response = self.client.post("/analyze/run", data={"source": "signal", "model": "yolo26s",
                                                          "use_scene_preset": "yes", "max_frames": "2",
                                                          "line_at": "0.2"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/runs/run_"))
        self.assertEqual(self.calls[0][2].line_at, .60)

    def test_photo_observation_keeps_original_and_downloadable_report(self):
        ok, encoded = cv2.imencode(".jpg", np.zeros((120, 180, 3), dtype=np.uint8))
        self.assertTrue(ok)
        response = self.client.post("/observations/new", data={
            "source": "photo", "photo": (io.BytesIO(encoded.tobytes()), "road.jpg"),
            "category": "Pothole / broken surface", "location": "Station Road at Market Road",
            "precise_location": "yes", "description": "Broken surface visible in the lane.",
            "media_date": "2026-11-13", "source_kind": "Team captured (reporter declared)",
            "box_left": "10", "box_top": "20", "box_right": "70", "box_bottom": "90",
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        record = load_records(self.data / "observations")[0]
        self.assertTrue((self.data / "observations" / record["original_media_file"]).is_file())
        report = self.client.get(f"/observations/{record['id']}/report")
        self.assertEqual(report.status_code, 200)
        self.assertIn(b"data:image/jpeg;base64,", report.data)


if __name__ == "__main__":
    unittest.main()
