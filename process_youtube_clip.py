from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def semitones_to_pitch_factor(semitones: float) -> float:
    """Convert a semitone offset to a linear pitch factor.

    Negative values shift down, positive values shift up.
    Examples: -1 → ~0.9439, +3 → ~1.1892, 0 → 1.0
    """
    return 2 ** (semitones / 12)


def hz_ratio_to_pitch_factor(reference_hz: float, target_hz: float) -> float:
    """Compute a linear pitch factor from a reference and target frequency in Hz.

    Example: reference_hz=450, target_hz=440 → 440/450 ≈ 0.9778 (slight shift down).
    """
    if reference_hz <= 0:
        raise ValueError(f"reference_hz must be positive, got {reference_hz}")
    if target_hz <= 0:
        raise ValueError(f"target_hz must be positive, got {target_hz}")
    return target_hz / reference_hz


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


def process_audio_pitch(input_file: Path, output_file: Path, pitch_factor: float) -> None:
    """Shift the audio pitch of *input_file* by *pitch_factor* and write to *output_file*.

    pitch_factor < 1 shifts down, > 1 shifts up, == 1 is unchanged.
    Video stream is copied without re-encoding.
    """
    tempo_compensation = 1.0 / pitch_factor

    if has_rubberband():
        audio_filter = f"rubberband=pitch={pitch_factor:.6f}:formant=preserved"
    else:
        sample_rate = get_audio_sample_rate(input_file)
        audio_filter = (
            f"asetrate={sample_rate}*{pitch_factor:.6f},"
            f"aresample={sample_rate},"
            f"atempo={tempo_compensation:.6f}"
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
        description=(
            "Download a YouTube clip section and shift its audio pitch.\n"
            "Pitch can be specified as semitones (--semitones) or as a Hz ratio\n"
            "(--ref-hz and --target-hz). Default: -1 semitone."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="Video URL")
    parser.add_argument("--start", default="00:00:00", help="Clip start time (default: 00:00:00)")
    parser.add_argument("--end", default="00:02:00", help="Clip end time (default: 00:02:00)")
    parser.add_argument(
        "--output",
        default="clip_medio_tono_abajo.mp4",
        help="Output MP4 file (default: clip_medio_tono_abajo.mp4)",
    )

    pitch_group = parser.add_argument_group(
        "pitch options (mutually exclusive — pick one method)"
    )
    pitch_group.add_argument(
        "--semitones",
        "--st",
        type=float,
        default=None,
        metavar="N",
        dest="semitones",
        help=(
            "Semitones to shift the pitch. Negative = down, positive = up. "
            "Examples: --semitones -1  --semitones +3  --st -2  (default: -1)"
        ),
    )
    pitch_group.add_argument(
        "--ref-hz",
        type=float,
        default=None,
        metavar="HZ",
        help=(
            "Reference pitch frequency in Hz (the pitch detected in the video). "
            "Must be combined with --target-hz. Example: --ref-hz 450 --target-hz 440"
        ),
    )
    pitch_group.add_argument(
        "--target-hz",
        type=float,
        default=None,
        metavar="HZ",
        help="Target pitch frequency in Hz. Must be combined with --ref-hz.",
    )

    return parser, parser.parse_args()


def resolve_pitch_factor(args: argparse.Namespace, parser: argparse.ArgumentParser) -> float:
    """Validate pitch-related arguments and return the resolved linear pitch factor."""
    hz_mode = (args.ref_hz is not None) or (args.target_hz is not None)
    st_mode = args.semitones is not None

    if hz_mode and st_mode:
        parser.error("--semitones/--st and --ref-hz/--target-hz are mutually exclusive.")

    if hz_mode:
        if args.ref_hz is None or args.target_hz is None:
            parser.error("--ref-hz and --target-hz must be used together.")
        return hz_ratio_to_pitch_factor(args.ref_hz, args.target_hz)

    semitones = args.semitones if st_mode else -1.0
    return semitones_to_pitch_factor(semitones)


def main() -> int:
    parser, args = parse_args()

    require_binary("ffmpeg")
    require_binary("ffprobe")

    pitch_factor = resolve_pitch_factor(args, parser)

    output_file = Path(args.output).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = Path(tmp_dir)
        downloaded_file = download_section(args.url, args.start, args.end, workdir)
        process_audio_pitch(downloaded_file, output_file, pitch_factor)

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
