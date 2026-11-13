"""Create reviewable VISTA release archives without environments or scratch files."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
FINAL_RUNS = (
    "colonel_by_yolo26s_final",
    "colonel_by_yolov8n_baseline",
    "intel_yolo26s_measured",
    "intel_yolov8n_baseline",
    "stopped_yolo26s",
    "kumasi_pothole_yolo26s",
    "cuttack_yolo26s",
    "bengaluru_night_yolo26s",
)
PYTHON_FILES = [
    ROOT / "README.md",
    ROOT / "package_project.py",
    *(ROOT / "phase2_prototype").glob("*.py"),
    ROOT / "phase2_prototype" / "README.md",
    ROOT / "phase2_prototype" / "requirements.txt",
    ROOT / "phase2_prototype" / "requirements_streamlit.txt",
    ROOT / "phase2_prototype" / "yolo26s.pt",
    ROOT / "phase2_prototype" / "yolov8n.pt",
    *(ROOT / "phase2_prototype" / "sample_data").glob("*"),
    *(ROOT / "phase2_prototype" / "evaluation_data").glob("*"),
    *(file for file in (ROOT / "phase2_prototype" / "observations").rglob("*") if file.is_file()),
    *(file for file in (ROOT / "phase2_prototype" / "actions").rglob("*") if file.is_file()),
    *(file for file in (ROOT / "phase2_prototype" / "web_ui").rglob("*") if file.is_file()),
    *(
        file
        for run in FINAL_RUNS
        for file in (ROOT / "phase2_prototype" / "runs" / run).glob("*")
        if file.is_file()
    ),
]
WEB_FILES = [
    *(
        file
        for folder in ("src", "public", "scripts")
        for file in (ROOT / "vista-web" / folder).rglob("*")
        if file.is_file()
    ),
    *(ROOT / "vista-web" / name for name in ("README.md", "package.json", "package-lock.json", "index.html", "browser.html", "vite.config.js", "vercel.json")),
]


def make_archive(name: str, files: list[Path]) -> Path:
    OUTPUT.mkdir(exist_ok=True)
    destination = OUTPUT / name
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(set(files)):
            if not file.is_file():
                raise FileNotFoundError(file)
            archive.write(file, file.relative_to(ROOT))
    with ZipFile(destination) as archive:
        broken = archive.testzip()
        if broken:
            raise OSError(f"Corrupt archive member: {broken}")
        print(f"{destination.name}: {len(archive.namelist())} files, {destination.stat().st_size / 1024**2:.1f} MiB")
    return destination


def main() -> None:
    make_archive("VISTA_Python_Project.zip", PYTHON_FILES)
    presentation = OUTPUT / "VISTA_Minor_Project_Proposal.pptx"
    if presentation.is_file() and all(file.is_file() for file in WEB_FILES):
        make_archive("VISTA_Complete_Project.zip", PYTHON_FILES + WEB_FILES + [presentation])


if __name__ == "__main__":
    main()
