# yt-trim-pitch

## Introduction

**yt-trim-pitch** is a command-line utility that downloads a time-bounded section of a YouTube video and shifts its audio pitch — useful for practising music, transcribing melodies, or listening to tracks at a different register without changing their speed.

The pitch shift can be specified in three ways:

| Method | Example | Notes |
|--------|---------|-------|
| Semitones (default) | `--semitones -1` | Negative = down, positive = up |
| Semitone shorthand | `--st +3` | Alias for `--semitones` |
| Hz ratio | `--ref-hz 450 --target-hz 440` | From detected pitch to desired pitch |

The default behaviour (no pitch flags) is **−1 semitone** (one semitone down).

---

## Project Description

The tool chains together two well-known open-source utilities:

- **yt-dlp** — downloads the requested clip section directly from YouTube (or any yt-dlp-supported source), merging the best available video and audio streams into a single MP4 file.
- **FFmpeg** — post-processes the downloaded clip, shifting the audio pitch by the requested amount while keeping video and tempo intact.

The result is a self-contained MP4 file ready for playback.

---

## Logic Description

The core processing pipeline lives in `process_youtube_clip.py` and follows these steps:

1. **Argument parsing** — accepts a video URL plus optional `--start`, `--end`, `--output`, and pitch arguments.
2. **Pitch factor resolution** (`resolve_pitch_factor`):
   - `--semitones N` / `--st N` → `pitch_factor = 2^(N/12)`
   - `--ref-hz F --target-hz T` → `pitch_factor = T / F`
   - No pitch flag → default `pitch_factor = 2^(-1/12) ≈ 0.943874`
3. **Binary checks** — verifies that `ffmpeg` and `ffprobe` are available in `PATH`.
4. **Download** (`download_section`) — calls `yt-dlp` with `--download-sections` to retrieve only the requested time window, forcing keyframe alignment at cut points for a clean trim.
5. **Pitch detection** (`has_rubberband`) — probes the local FFmpeg build for the `rubberband` filter, which is the highest-quality option for pitch shifting.
6. **Pitch shifting** (`process_audio_pitch`):
   - *If rubberband is available*: uses `rubberband=pitch=<factor>:formant=preserved` — preserves formants for a more natural sound.
   - *If rubberband is not available*: falls back to the `asetrate` + `aresample` + `atempo` filter chain. The tempo is corrected by applying `atempo = 1 / pitch_factor` after the rate change.
7. **Output** — writes the processed video to the path specified by `--output` (default: `clip_medio_tono_abajo.mp4`).

The PowerShell setup script (`setup_and_run_video_pitch.ps1`) handles first-time installation: it locates or creates a Conda environment, installs pip dependencies, ensures FFmpeg is on the system `PATH` (installing it via `winget` if necessary), and then delegates to `process_youtube_clip.py` for the full pipeline.

---

## Installation and First Run (Windows)

> **Prerequisites:** [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (or Anaconda / Miniforge) and Windows Package Manager (`winget`, included with Windows 10/11).

1. Clone or download this repository.
2. Open `setup_and_run_video_pitch.ps1` in a text editor and replace the placeholder value:
   ```powershell
   $VideoUrl = 'PASTE_YOUR_VIDEO_URL_HERE'
   ```
   with the actual YouTube URL you want to process. Optionally adjust `$StartTime`, `$EndTime`, `$OutputFileName`, and the pitch variables (see below).
3. Right-click the file and choose **Run with PowerShell** (the script will request Administrator privileges automatically if needed), or run from a PowerShell terminal:
   ```powershell
   .\setup_and_run_video_pitch.ps1
   ```

### Configuring the pitch shift in the PS1 file

Near the top of the script there are three variables — set **one** option and leave the other as `$null`:

```powershell
# Option A — semitones (default: -1)
$Semitones = -1    # change to any integer or decimal, e.g. +3, -2, 0.5
$RefHz    = $null
$TargetHz = $null

# Option B — Hz ratio (comment out Option A lines above)
$Semitones = $null
$RefHz    = 450    # pitch detected in the video
$TargetHz = 440    # pitch you want in the output
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
2. Set the variables at the top:
   ```bat
   set VIDEO_URL=https://www.youtube.com/watch?v=YOUR_VIDEO_ID
   set START_TIME=00:00:00
   set END_TIME=00:02:00
   set OUTPUT_FILE=clip_medio_tono_abajo.mp4

   rem Semitone mode (default):
   set PITCH_ARGS=--semitones -1

   rem Hz ratio mode (alternative):
   rem set PITCH_ARGS=--ref-hz 450 --target-hz 440
   ```
3. Double-click the file or run it from a Command Prompt.

> **Note:** The BAT file assumes `python` resolves to the interpreter in your active Conda environment. Activate `VIDEO_PITCH_ENV` first if needed:
> ```bat
> conda activate VIDEO_PITCH_ENV
> run_video_pitch_down.bat
> ```

---

## Direct CLI Usage

```bash
# Default: one semitone down
python process_youtube_clip.py "https://www.youtube.com/watch?v=..." --start 00:01:30 --end 00:03:00

# Semitone shorthand (--st is an alias for --semitones)
python process_youtube_clip.py "URL" --st -2
python process_youtube_clip.py "URL" --semitones +3

# Hz ratio: detected A4 = 450 Hz, want standard A4 = 440 Hz
python process_youtube_clip.py "URL" --ref-hz 450 --target-hz 440

# Custom output file
python process_youtube_clip.py "URL" --start 00:00:30 --end 00:02:00 --output my_clip.mp4 --semitones -1
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
