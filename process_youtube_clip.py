from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SEMITONE_DOWN_FACTOR = 2 ** (-1 / 12)
TEMPO_COMPENSATION = 2 ** (1 / 12)


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required executable not found in PATH: {name}")


def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True)


def capture_command(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def find_downloaded_file(directory: Path) -> Path:
    files = [p for p in directory.iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("No downloaded file was found.")
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def has_rubberband() -> bool:
    try:
        output = capture_command(["ffmpeg", "-hide_banner", "-filters"])
    except Exception:
        return False
    return "rubberband" in output


def get_audio_sample_rate(input_file: Path) -> int:
    output = capture_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(input_file),
        ]
    )
    try:
        return int(output)
    except ValueError as exc:
        raise RuntimeError(f"Could not read audio sample rate from file: {input_file}") from exc



def download_section(url: str, start: str, end: str, workdir: Path) -> Path:
    output_template = workdir / "clip.%(ext)s"
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--download-sections",
        f"*{start}-{end}",
        "--force-keyframes-at-cuts",
        "-o",
        str(output_template),
        url,
    ]
    run_command(cmd)
    return find_downloaded_file(workdir)



def process_audio_pitch(input_file: Path, output_file: Path) -> None:
    if has_rubberband():
        audio_filter = f"rubberband=pitch={SEMITONE_DOWN_FACTOR:.6f}:formant=preserved"
    else:
        sample_rate = get_audio_sample_rate(input_file)
        audio_filter = (
            f"asetrate={sample_rate}*{SEMITONE_DOWN_FACTOR:.6f},"
            f"aresample={sample_rate},"
            f"atempo={TEMPO_COMPENSATION:.6f}"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-c:v",
        "copy",
        "-af",
        audio_filter,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_file),
    ]
    run_command(cmd)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a YouTube clip section and lower its audio by one semitone."
    )
    parser.add_argument("url", help="Video URL")
    parser.add_argument("--start", default="00:00:00", help="Clip start time, default: 00:00:00")
    parser.add_argument("--end", default="00:02:00", help="Clip end time, default: 00:02:00")
    parser.add_argument(
        "--output",
        default="clip_medio_tono_abajo.mp4",
        help="Output MP4 file, default: clip_medio_tono_abajo.mp4",
    )
    return parser.parse_args()



def main() -> int:
    args = parse_args()

    require_binary("ffmpeg")
    require_binary("ffprobe")

    output_file = Path(args.output).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = Path(tmp_dir)
        downloaded_file = download_section(args.url, args.start, args.end, workdir)
        process_audio_pitch(downloaded_file, output_file)

    print(f"Saved processed file to: {output_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
