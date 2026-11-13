import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from observations import add_record, frame_at, load_records, marked_jpeg, pattern_for, report_html


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.details = {
            "category": "Pothole / broken surface",
            "location": "Main Road at Station Road",
            "description": "Broken asphalt visible in the near lane.",
            "source_kind": "Team captured (reporter declared)",
            "media_key": "photo-a",
            "media_date": "2026-11-01",
            "precise_location": True,
        }
        self.image = marked_jpeg(np.zeros((100, 200, 3), dtype=np.uint8), (.1, .2, .8, .9))

    def tearDown(self):
        self.temp.cleanup()

    def test_evidence_is_saved_with_record(self):
        record = add_record(self.folder, self.details, self.image, original_media=b"photo-bytes")
        self.assertEqual(load_records(self.folder)[0]["id"], record["id"])
        self.assertEqual((self.folder / record["evidence_file"]).read_bytes(), self.image)
        self.assertEqual((self.folder / record["original_media_file"]).read_bytes(), b"photo-bytes")

    def test_recurrence_requires_separate_media_and_dates(self):
        first = add_record(self.folder, self.details, self.image)
        same_media = add_record(self.folder, self.details, self.image)
        self.assertFalse(pattern_for(first, [first, same_media])["recurrence_supported"])
        second = add_record(self.folder, {**self.details, "media_key": "photo-b", "media_date": "2026-11-02"}, self.image)
        self.assertTrue(pattern_for(first, [first, second])["recurrence_supported"])

    def test_approximate_location_never_claims_recurrence(self):
        first = add_record(self.folder, {**self.details, "location": "Kumasi, exact road unknown", "precise_location": False}, self.image)
        second = add_record(self.folder, {**self.details, "location": "Kumasi, exact road unknown", "precise_location": False, "media_key": "photo-b", "media_date": "2026-11-02"}, self.image)
        self.assertFalse(pattern_for(first, [first, second])["recurrence_supported"])

    def test_report_embeds_evidence_and_escapes_user_text(self):
        record = add_record(self.folder, {**self.details, "description": "<script>alert(1)</script>"}, self.image)
        page = report_html(record, [record], self.image)
        self.assertIn("data:image/jpeg;base64,", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn("recurring pattern is not established", page)

    def test_frame_at_rejects_time_beyond_video(self):
        video = self.folder / "sample.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
        for _ in range(10):
            writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
        writer.release()
        self.assertEqual(frame_at(video, .5).shape[:2], (64, 64))
        with self.assertRaises(ValueError):
            frame_at(video, 1.0)


if __name__ == "__main__":
    unittest.main()
