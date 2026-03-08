"""Tests for process_youtube_clip.py"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from process_youtube_clip import (
    SEMITONE_DOWN_FACTOR,
    TEMPO_COMPENSATION,
    capture_command,
    find_downloaded_file,
    get_audio_sample_rate,
    has_rubberband,
    require_binary,
    run_command,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_semitone_down_factor_approx(self):
        assert abs(SEMITONE_DOWN_FACTOR - 0.943874) < 1e-5

    def test_tempo_compensation_approx(self):
        assert abs(TEMPO_COMPENSATION - 1.059463) < 1e-5

    def test_factors_are_inverses(self):
        """Shifting pitch down then compensating tempo should cancel out to ~1."""
        assert abs(SEMITONE_DOWN_FACTOR * TEMPO_COMPENSATION - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# require_binary
# ---------------------------------------------------------------------------

class TestRequireBinary:
    def test_raises_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="Required executable not found"):
                require_binary("nonexistent_tool")

    def test_passes_when_binary_present(self):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            require_binary("ffmpeg")  # should not raise


# ---------------------------------------------------------------------------
# run_command / capture_command
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_returns_completed_process(self):
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = run_command(["echo", "hello"])
            mock_run.assert_called_once_with(["echo", "hello"], check=True, text=True)
            assert result is mock_result

    def test_propagates_called_process_error(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
            with pytest.raises(subprocess.CalledProcessError):
                run_command(["bad_cmd"])


class TestCaptureCommand:
    def test_returns_stripped_stdout(self):
        mock_result = MagicMock()
        mock_result.stdout = "  44100  \n"
        with patch("subprocess.run", return_value=mock_result):
            output = capture_command(["ffprobe", "-version"])
        assert output == "44100"

    def test_propagates_error_on_nonzero_exit(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
            with pytest.raises(subprocess.CalledProcessError):
                capture_command(["bad_cmd"])


# ---------------------------------------------------------------------------
# find_downloaded_file
# ---------------------------------------------------------------------------

class TestFindDownloadedFile:
    def test_raises_when_directory_empty(self, tmp_path):
        with pytest.raises(RuntimeError, match="No downloaded file was found"):
            find_downloaded_file(tmp_path)

    def test_returns_most_recently_modified_file(self, tmp_path):
        old_file = tmp_path / "old.mp4"
        new_file = tmp_path / "new.mp4"
        old_file.write_text("old")
        new_file.write_text("new")

        import time
        time.sleep(0.01)
        new_file.touch()

        result = find_downloaded_file(tmp_path)
        assert result == new_file

    def test_ignores_directories(self, tmp_path):
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        file = tmp_path / "clip.mp4"
        file.write_text("data")

        result = find_downloaded_file(tmp_path)
        assert result == file


# ---------------------------------------------------------------------------
# has_rubberband
# ---------------------------------------------------------------------------

class TestHasRubberband:
    def test_returns_true_when_rubberband_in_filters(self):
        with patch(
            "process_youtube_clip.capture_command",
            return_value="... rubberband  A->A Apply time-stretching ...",
        ):
            assert has_rubberband() is True

    def test_returns_false_when_rubberband_not_in_filters(self):
        with patch(
            "process_youtube_clip.capture_command",
            return_value="aecho\naresample\natempo",
        ):
            assert has_rubberband() is False

    def test_returns_false_when_ffmpeg_fails(self):
        with patch(
            "process_youtube_clip.capture_command",
            side_effect=RuntimeError("ffmpeg not found"),
        ):
            assert has_rubberband() is False


# ---------------------------------------------------------------------------
# get_audio_sample_rate
# ---------------------------------------------------------------------------

class TestGetAudioSampleRate:
    def test_returns_integer_sample_rate(self, tmp_path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_text("")
        with patch("process_youtube_clip.capture_command", return_value="44100"):
            rate = get_audio_sample_rate(fake_file)
        assert rate == 44100

    def test_raises_on_non_numeric_output(self, tmp_path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_text("")
        with patch("process_youtube_clip.capture_command", return_value="N/A"):
            with pytest.raises(RuntimeError, match="Could not read audio sample rate"):
                get_audio_sample_rate(fake_file)

    def test_raises_on_empty_output(self, tmp_path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_text("")
        with patch("process_youtube_clip.capture_command", return_value=""):
            with pytest.raises(RuntimeError, match="Could not read audio sample rate"):
                get_audio_sample_rate(fake_file)
