# Included footage and permitted uses

The source URLs below identify footage captured by other people. VISTA's MP4 copies are conversions for local analysis; no clip is presented as footage captured by the VISTA team.

| Local file | Source and creator | License | Conversion | Role |
| --- | --- | --- | --- | --- |
| colonel_by_signal_10fps.mp4 | [Temporary traffic signal at Colonel By Drive](https://commons.wikimedia.org/wiki/File:Temporary_traffic_signal_at_Colonel_By_Drive.webm), Wikimedia Commons user 137a | CC0 1.0 | 1920×1080 original to 960×540, 10 fps, audio removed | Manually audited signal clip |
| intel_car_detection.mp4 | [Intel IoT DevKit car-detection.mp4](https://github.com/intel-iot-devkit/sample-videos) | CC BY 4.0 | Source sample unchanged | Manually audited overhead road clip |
| cuttack_link_road_30s.mp4 | [Moving vehicles in Link road, Cuttack, Odisha](https://commons.wikimedia.org/wiki/File:Moving_vehicles_in_Link_road,_Cuttack,_Odisha.webm), Subhashish Panigrahi | CC BY-SA 3.0 | 40–70 s segment, 960×540, 10 fps, audio removed | India daytime scene test, no complete manual event labels |
| bengaluru_night_20s.mp4 | [Ramana Maharshi Road, Bangalore (2025) 02](https://commons.wikimedia.org/wiki/File:Ramana_Maharshi_Road,_Bangalore_(2025)_02.webm), Gpkp | CC BY-SA 4.0 | First 20 s of Wikimedia 480p transcode, 10 fps, audio removed | India night congestion scene test, no complete manual event labels |
| kumasi_pothole_10fps.mp4 | [Cars Moving into pothole](https://commons.wikimedia.org/wiki/File:Cars_Moving_into_pothole.webm), Amuzujoe | CC BY-SA 4.0 | Wikimedia 480p transcode to 10 fps MP4, audio removed | Manually marked road issue; traffic-event outputs unvalidated |
| stopped_demo.mp4 | Intel sample above | CC BY 4.0 derivative | One video frame frozen for six seconds | Synthetic stop-rule test only |

The observation records also include a [public still photograph of potholes in Jodhpur Park, Kolkata](https://commons.wikimedia.org/wiki/File:Potholes_(1_November_2026).jpg), by Sbb1413, licensed CC BY-SA 3.0. VISTA stores a 1280-pixel copy and a manually marked derivative in `observations/media/` and `observations/evidence/`. The source lists camera coordinates (22.503136, 88.364902), which indicate an area to search, not the exact defect point. Its stated media date is 2026-11-01. The photo was not captured by the VISTA team and the current road condition has not been field-verified.

The Cuttack source identifies Link Road and a camera position in Odisha. The Bengaluru source identifies Ramana Maharshi Road and a camera position. Neither India clip is evidence of a pothole; they are traffic scenes. The Kumasi source describes a damaged road section but does not give a precise road or junction. The marked evidence frame and report retain the original creator and license. A road-issue report is a reviewer-authored observation, not an automated defect diagnosis.
