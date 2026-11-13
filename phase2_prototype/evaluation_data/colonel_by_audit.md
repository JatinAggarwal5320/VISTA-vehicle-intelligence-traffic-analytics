# Manual crossing audit: Colonel By Drive signal

Source: [Temporary traffic signal at Colonel By Drive](https://commons.wikimedia.org/wiki/File:Temporary_traffic_signal_at_Colonel_By_Drive.webm), by Wikimedia Commons user **137a**, released under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The included `sample_data/colonel_by_signal_10fps.mp4` is a 960 × 540, 10 fps H.264 conversion of the original 20-second fixed-camera clip; audio was removed. The original camera view is not otherwise altered.

Seven cars visibly pass a horizontal line at 60% of frame height in the
left travel lane. The CSV timestamps are midpoint estimates from half-second
visual review of the original footage, using each vehicle's bottom-center:

| Interval (s) | Direction |
|---|---|
| 2.5–3.0 | top to bottom |
| 5.0–5.5 | top to bottom |
| 8.5–9.0 | top to bottom |
| 11.5–12.0 | top to bottom |
| 13.0–13.5 | top to bottom |
| 16.5–17.0 | top to bottom |
| 19.0–19.5 | top to bottom |

The right-side vehicles are partly cropped and their tracks move or switch
IDs. No visible-stop events were labeled from this clip. The frozen-frame stop
clip is a separate synthetic test of the rule, and is not included in the
real-video accuracy comparison.

This is a small, single-reviewer audit, not a general benchmark. A second
team member should confirm the labels before formal reporting.
