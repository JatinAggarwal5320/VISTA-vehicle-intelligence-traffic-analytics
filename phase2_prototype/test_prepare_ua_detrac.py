import tempfile
import unittest
from pathlib import Path

from prepare_ua_detrac import annotation_crossings


class UaDetracTests(unittest.TestCase):
    def test_annotations_yield_one_directional_crossing_per_track(self):
        xml = """<sequence name="demo">
          <frame num="1"><target_list><target id="7"><box left="40" top="20" width="20" height="20"/><attribute vehicle_type="car"/></target></target_list></frame>
          <frame num="2"><target_list><target id="7"><box left="40" top="40" width="20" height="20"/><attribute vehicle_type="car"/></target></target_list></frame>
          <frame num="3"><target_list><target id="7"><box left="40" top="60" width="20" height="20"/><attribute vehicle_type="car"/></target></target_list></frame>
          <frame num="4"><target_list><target id="7"><box left="40" top="65" width="20" height="20"/><attribute vehicle_type="car"/></target></target_list></frame>
        </sequence>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.xml"
            path.write_text(xml)
            events = annotation_crossings(path, first_frame=1, last_frame=4, fps=25, width=100, height=100, axis="y", line_fraction=.5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "top_to_bottom")
        self.assertEqual(events[0]["target_id"], 7)


if __name__ == "__main__":
    unittest.main()
