# Manual crossing audit: Intel sample

Source: Intel IoT DevKit `car-detection.mp4`, included as
`../sample_data/intel_car_detection.mp4` under CC BY 4.0. The full 30.16-second
clip was reviewed at one-second spacing, with half-second checks around each
vehicle crossing. Four cars visibly cross a horizontal line at 55% of frame
height. The timestamp in the CSV is the midpoint of the half-second interval
where each car's **bottom-center** crosses the line:

| Interval (s) | Direction |
|---|---|
| 6.5–7.0 | bottom to top |
| 16.0–16.5 | top to bottom |
| 17.0–17.5 | bottom to top |
| 26.0–26.5 | top to bottom |

These labels were created from visual review of the original video, without
using the model's boxes. They cover line crossings only; the moving clip has
no labeled stop events. This is a small, single-reviewer audit for checking the
pipeline, not a statistically useful accuracy benchmark. A second team member
should confirm the labels before citing them in a formal report.
