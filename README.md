# yt-trim-pitch

## Introduction

**yt-trim-pitch** is a small command-line utility that downloads a time-bounded section of a YouTube video and lowers its audio pitch by exactly one semitone — useful for practising music, transcribing melodies, or simply listening to tracks at a slightly different register without changing their speed.

---

## Project Description

The tool chains together two well-known open-source utilities:

- **yt-dlp** — downloads the requested clip section directly from YouTube (or any yt-dlp-supported source), merging the best available video and audio streams into a single MP4 file.
- **FFmpeg** — post-processes the downloaded clip, shifting the audio pitch down by one semitone while keeping video and tempo intact.

The result is a self-contained MP4 file ready for playback.

---

## Logic Description

The core processing pipeline lives in `process_youtube_clip.py` and follows these steps:

1. **Argument parsing** — accepts a video URL plus optional `--start`, `--end`, and `--output` arguments.
2. **Binary checks** — verifies that `ffmpeg` and `ffprobe` are available in `PATH` before attempting any work.
3. **Download** (`download_section`) — calls `yt-dlp` with `--download-sections` to retrieve only the requested time window, forcing keyframe alignment at the cut points for a clean trim.
4. **Pitch detection** (`has_rubberband`) — probes the local FFmpeg build for the `rubberband` filter. This filter is the highest-quality option for pitch shifting but requires FFmpeg to be compiled with librubberband support.
5. **Pitch shifting** (`process_audio_pitch`):
   - *If rubberband is available*: uses `rubberband=pitch=<factor>:formant=preserved` — preserves formants for a more natural sound.
   - *If rubberband is not available*: falls back to the `asetrate` + `aresample` + `atempo` filter chain, which resamples the audio to simulate the pitch shift and then corrects the tempo drift.
   - The semitone-down factor is `2^(-1/12) ≈ 0.943874`.
6. **Output** — writes the processed video to the path specified by `--output` (default: `clip_medio_tono_abajo.mp4`).

The PowerShell setup script (`setup_and_run_video_pitch.ps1`) mirrors this logic for a one-shot first-time installation: it locates or creates a Conda environment, installs pip dependencies, ensures FFmpeg is on the system `PATH` (installing it via `winget` if necessary), and then runs the full pipeline.

---

## Installation and First Run (Windows)

> **Prerequisites:** [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (or Anaconda / Miniforge) and Windows Package Manager (`winget`, included with Windows 10/11).

1. Clone or download this repository.
2. Open the file `setup_and_run_video_pitch.ps1` in a text editor and replace the placeholder value:
   ```powershell
   $VideoUrl = 'PASTE_YOUR_VIDEO_URL_HERE'
   ```
   with the actual YouTube URL you want to process. Optionally adjust `$StartTime`, `$EndTime`, and `$OutputFileName`.
3. Right-click the file and choose **Run with PowerShell** (the script will request Administrator privileges automatically if needed), or run from a PowerShell terminal:
   ```powershell
   .\setup_and_run_video_pitch.ps1
   ```

The script will:
- Locate your Conda installation.
- Create a new Conda environment called `VIDEO_PITCH_ENV` with Python 3.11 (or clone an existing environment if you set `$SourceEnvName`).
- Install `yt-dlp` from `requirements.txt`.
- Install FFmpeg system-wide via `winget` if it is not already present.
- Download and process the requested video clip.

The processed file is saved in the same directory as the script.

---

## Daily Usage (BAT file)

Once the environment is set up, use `run_video_pitch_down.bat` for quick re-runs:

1. Open `run_video_pitch_down.bat` in a text editor.
2. Set the variables at the top of the file to your desired values:
   ```bat
   set VIDEO_URL=https://www.youtube.com/watch?v=YOUR_VIDEO_ID
   set START_TIME=00:00:00
   set END_TIME=00:02:00
   set OUTPUT_FILE=clip_medio_tono_abajo.mp4
   ```
3. Double-click the file (or run it from a Command Prompt) — it will invoke `process_youtube_clip.py` with the configured parameters.

> **Note:** The BAT file assumes that `python` resolves to the interpreter in your active Conda environment and that `ffmpeg`/`ffprobe` are on `PATH`. Activate the `VIDEO_PITCH_ENV` environment first if needed:
> ```bat
> conda activate VIDEO_PITCH_ENV
> run_video_pitch_down.bat
> ```

You can also call the script directly for full control:
```bash
python process_youtube_clip.py "https://www.youtube.com/watch?v=..." --start 00:01:30 --end 00:03:00 --output my_clip.mp4
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `yt-dlp >= 2025.0.0` | YouTube / web video download |
| `ffmpeg` (system) | Audio/video processing and pitch shifting |
| `ffprobe` (system) | Audio stream inspection |

Install Python dependencies with:
```bash
pip install -r requirements.txt
```

---

## Contributors

| Name | Role | Date |
|------|------|------|
| Fernando Peñaherrera V. | Author | 2026-03-08 |

---

## License

This project is released under the [MIT License](LICENSE).
