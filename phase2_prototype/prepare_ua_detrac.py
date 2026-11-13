"""Turn one extracted UA-DETRAC image sequence and XML into a VISTA test clip.

Official download: https://sites.google.com/view/daweidu/projects/ua-detrac
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree


OFFICIAL_SOURCE = "https://sites.google.com/view/daweidu/projects/ua-detrac"


def frame_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    if not match:
        raise ValueError(f"Image name has no frame number: {path.name}")
    return int(match.group(1))


def annotation_crossings(
    xml_path: Path,
    *,
    first_frame: int,
    last_frame: int,
    fps: float,
    width: int,
    height: int,
    axis: str,
    line_fraction: float,
    margin_px: float = 5.0,
) -> list[dict]:
    if axis not in ("x", "y") or not 0 < line_fraction < 1 or fps <= 0:
        raise ValueError("Invalid line axis, position or frame rate")
    root = ElementTree.parse(xml_path).getroot()
    line = line_fraction * (width if axis == "x" else height)
    sides: dict[int, int] = {}
    counted: set[tuple[int, str]] = set()
    events = []
    for frame in sorted(root.findall(".//frame"), key=lambda item: int(item.attrib["num"])):
        number = int(frame.attrib["num"])
        if number < first_frame or number > last_frame:
            continue
        for target in frame.findall("./target_list/target"):
            target_id = int(target.attrib["id"])
            box = target.find("box")
            if box is None:
                continue
            left = float(box.attrib["left"])
            top = float(box.attrib["top"])
            box_width = float(box.attrib["width"])
            box_height = float(box.attrib["height"])
            position = left + box_width / 2 if axis == "x" else top + box_height
            side = -1 if position < line - margin_px else 1 if position > line + margin_px else 0
            if side == 0:
                continue
            previous = sides.get(target_id)
            if previous is not None and previous != side:
                direction = (
                    ("left_to_right" if side > 0 else "right_to_left") if axis == "x"
                    else ("top_to_bottom" if side > 0 else "bottom_to_top")
                )
                if (target_id, direction) not in counted:
                    attribute = target.find("attribute")
                    events.append({
                        "type": "crossing",
                        "time_s": round((number - first_frame) / fps, 3),
                        "direction": direction,
                        # UA-DETRAC classes and COCO classes do not map one-to-one.
                        # Count-only evaluation checks time and direction by default.
                        "vehicle_class": "",
                        "source_vehicle_type": attribute.attrib.get("vehicle_type", "") if attribute is not None else "",
                        "target_id": target_id,
                        "frame_num": number,
                    })
                    counted.add((target_id, direction))
            sides[target_id] = side
    return events


def prepare_sequence(
    image_dir: Path,
    xml_path: Path,
    output_dir: Path,
    *,
    fps: float = 25.0,
    start_frame: int = 1,
    frame_count: int = 750,
    axis: str = "y",
    line_fraction: float = 0.55,
) -> dict:
    import cv2
    import imageio_ffmpeg

    if frame_count <= 0 or start_frame <= 0:
        raise ValueError("start_frame and frame_count must be positive")
    images = sorted(
        (path for path in image_dir.iterdir() if path.suffix.lower() in (".jpg", ".jpeg", ".png")),
        key=frame_number,
    )
    selected = [path for path in images if start_frame <= frame_number(path) < start_frame + frame_count]
    if not selected:
        raise ValueError("No images in the requested frame range")
    numbers = [frame_number(path) for path in selected]
    if numbers != list(range(numbers[0], numbers[-1] + 1)):
        raise ValueError("The selected image frames must be consecutive")
    first = cv2.imread(str(selected[0]))
    if first is None:
        raise ValueError(f"Cannot decode {selected[0]}")
    height, width = first.shape[:2]
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = output_dir / "clip_raw.mp4"
    writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Could not create MP4 writer")
    try:
        for image_path in selected:
            frame = cv2.imread(str(image_path))
            if frame is None or frame.shape[:2] != (height, width):
                raise ValueError(f"Missing or inconsistent image: {image_path}")
            writer.write(frame)
    finally:
        writer.release()
    clip = output_dir / "clip.mp4"
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(raw),
        "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(clip),
    ], check=True)
    raw.unlink()

    labels = annotation_crossings(
        xml_path, first_frame=frame_number(selected[0]), last_frame=frame_number(selected[-1]),
        fps=fps, width=width, height=height, axis=axis, line_fraction=line_fraction,
    )
    label_file = output_dir / "labels.csv"
    with label_file.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["type", "time_s", "direction", "vehicle_class", "source_vehicle_type", "target_id", "frame_num"])
        writer.writeheader()
        writer.writerows(labels)
    info = {
        "source": OFFICIAL_SOURCE,
        "sequence": image_dir.name,
        "annotation_file": xml_path.name,
        "first_frame": frame_number(selected[0]),
        "last_frame": frame_number(selected[-1]),
        "fps": fps,
        "width": width,
        "height": height,
        "axis": axis,
        "line_fraction": line_fraction,
        "crossing_labels": len(labels),
    }
    (output_dir / "source_info.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="One extracted UA-DETRAC sequence image folder")
    parser.add_argument("--xml", type=Path, required=True, help="Matching UA-DETRAC sequence XML")
    parser.add_argument("--output", type=Path, required=True, help="Destination for clip.mp4 and labels.csv")
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--start-frame", type=int, default=1)
    parser.add_argument("--frames", type=int, default=750)
    parser.add_argument("--axis", choices=("x", "y"), default="y")
    parser.add_argument("--line", type=float, default=0.55)
    args = parser.parse_args()
    print(json.dumps(prepare_sequence(
        args.images, args.xml, args.output, fps=args.fps, start_frame=args.start_frame,
        frame_count=args.frames, axis=args.axis, line_fraction=args.line,
    ), indent=2))


if __name__ == "__main__":
    main()
