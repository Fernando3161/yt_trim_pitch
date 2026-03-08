"""Tests for process_youtube_clip.py"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from process_youtube_clip import (
    capture_command,
    find_downloaded_file,
    get_audio_sample_rate,
    has_rubberband,
    hz_ratio_to_pitch_factor,
    process_audio_pitch,
    require_binary,
    resolve_pitch_factor,
    run_command,
    semitones_to_pitch_factor,
)


# ---------------------------------------------------------------------------
# semitones_to_pitch_factor
# ---------------------------------------------------------------------------

class TestSemitonesToPitchFactor:
    def test_minus_one_semitone(self):
        factor = semitones_to_pitch_factor(-1)
        assert abs(factor - 0.943874) < 1e-5

    def test_plus_one_semitone(self):
        factor = semitones_to_pitch_factor(1)
        assert abs(factor - 1.059463) < 1e-5

    def test_zero_semitones_is_unity(self):
        assert semitones_to_pitch_factor(0) == 1.0

    def test_octave_down_is_half(self):
        assert abs(semitones_to_pitch_factor(-12) - 0.5) < 1e-10

    def test_octave_up_is_double(self):
        assert abs(semitones_to_pitch_factor(12) - 2.0) < 1e-10

    def test_up_down_same_magnitude_cancel(self):
        """Shifting up then down by the same amount should give factor 1."""
        factor = semitones_to_pitch_factor(3) * semitones_to_pitch_factor(-3)
        assert abs(factor - 1.0) < 1e-10

    def test_minus_one_and_plus_one_are_inverses(self):
        """The -1 st factor and +1 st factor should multiply to 1."""
        assert abs(semitones_to_pitch_factor(-1) * semitones_to_pitch_factor(1) - 1.0) < 1e-10

    def test_fractional_semitones(self):
        factor = semitones_to_pitch_factor(0.5)
        assert 1.0 < factor < semitones_to_pitch_factor(1)


# ---------------------------------------------------------------------------
# hz_ratio_to_pitch_factor
# ---------------------------------------------------------------------------

class TestHzRatioToPitchFactor:
    def test_a440_to_a450_shifts_up(self):
        factor = hz_ratio_to_pitch_factor(reference_hz=440, target_hz=450)
        assert factor > 1.0

    def test_a450_to_a440_shifts_down(self):
        factor = hz_ratio_to_pitch_factor(reference_hz=450, target_hz=440)
        assert abs(factor - 440 / 450) < 1e-10

    def test_same_frequency_is_unity(self):
        assert hz_ratio_to_pitch_factor(440, 440) == 1.0

    def test_raises_on_zero_reference(self):
        with pytest.raises(ValueError, match="reference_hz must be positive"):
            hz_ratio_to_pitch_factor(0, 440)

    def test_raises_on_negative_reference(self):
        with pytest.raises(ValueError, match="reference_hz must be positive"):
            hz_ratio_to_pitch_factor(-10, 440)

    def test_raises_on_zero_target(self):
        with pytest.raises(ValueError, match="target_hz must be positive"):
            hz_ratio_to_pitch_factor(440, 0)

    def test_raises_on_negative_target(self):
        with pytest.raises(ValueError, match="target_hz must be positive"):
            hz_ratio_to_pitch_factor(440, -5)


# ---------------------------------------------------------------------------
# resolve_pitch_factor
# ---------------------------------------------------------------------------

class TestResolvePitchFactor:
    def _make_parser(self):
        """Return a minimal parser that mirrors the real one's dest names."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--semitones", type=float, default=None, dest="semitones")
        parser.add_argument("--ref-hz", type=float, default=None)
        parser.add_argument("--target-hz", type=float, default=None)
        return parser

    def test_default_is_minus_one_semitone(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        factor = resolve_pitch_factor(args, parser)
        assert abs(factor - semitones_to_pitch_factor(-1)) < 1e-10

    def test_explicit_semitones(self):
        parser = self._make_parser()
        args = parser.parse_args(["--semitones", "3"])
        factor = resolve_pitch_factor(args, parser)
        assert abs(factor - semitones_to_pitch_factor(3)) < 1e-10

    def test_hz_mode(self):
        parser = self._make_parser()
        args = parser.parse_args(["--ref-hz", "450", "--target-hz", "440"])
        factor = resolve_pitch_factor(args, parser)
        assert abs(factor - hz_ratio_to_pitch_factor(450, 440)) < 1e-10

    def test_mutual_exclusion_raises(self):
        parser = self._make_parser()
        args = parser.parse_args(["--semitones", "-1", "--ref-hz", "450", "--target-hz", "440"])
        with pytest.raises(SystemExit):
            resolve_pitch_factor(args, parser)

    def test_missing_target_hz_raises(self):
        parser = self._make_parser()
        args = parser.parse_args(["--ref-hz", "450"])
        with pytest.raises(SystemExit):
            resolve_pitch_factor(args, parser)

    def test_missing_ref_hz_raises(self):
        parser = self._make_parser()
        args = parser.parse_args(["--target-hz", "440"])
        with pytest.raises(SystemExit):
            resolve_pitch_factor(args, parser)


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


# ---------------------------------------------------------------------------
# process_audio_pitch
# ---------------------------------------------------------------------------

class TestProcessAudioPitch:
    def _fake_file(self, tmp_path) -> Path:
        f = tmp_path / "input.mp4"
        f.write_text("")
        return f

    def test_uses_rubberband_filter_when_available(self, tmp_path):
        input_file = self._fake_file(tmp_path)
        output_file = tmp_path / "out.mp4"
        pitch_factor = semitones_to_pitch_factor(-1)

        with patch("process_youtube_clip.has_rubberband", return_value=True), \
             patch("process_youtube_clip.run_command") as mock_run:
            process_audio_pitch(input_file, output_file, pitch_factor)

        cmd = mock_run.call_args[0][0]
        af_value = cmd[cmd.index("-af") + 1]
        assert "rubberband" in af_value
        assert f"{pitch_factor:.6f}" in af_value

    def test_uses_fallback_filter_when_no_rubberband(self, tmp_path):
        input_file = self._fake_file(tmp_path)
        output_file = tmp_path / "out.mp4"
        pitch_factor = semitones_to_pitch_factor(-1)

        with patch("process_youtube_clip.has_rubberband", return_value=False), \
             patch("process_youtube_clip.get_audio_sample_rate", return_value=44100), \
             patch("process_youtube_clip.run_command") as mock_run:
            process_audio_pitch(input_file, output_file, pitch_factor)

        cmd = mock_run.call_args[0][0]
        af_value = cmd[cmd.index("-af") + 1]
        assert "asetrate" in af_value
        assert "aresample" in af_value
        assert "atempo" in af_value

    def test_tempo_compensation_is_inverse_of_pitch_factor(self, tmp_path):
        """atempo value should equal 1/pitch_factor to preserve tempo."""
        input_file = self._fake_file(tmp_path)
        output_file = tmp_path / "out.mp4"
        pitch_factor = semitones_to_pitch_factor(3)
        expected_tempo = 1.0 / pitch_factor

        with patch("process_youtube_clip.has_rubberband", return_value=False), \
             patch("process_youtube_clip.get_audio_sample_rate", return_value=48000), \
             patch("process_youtube_clip.run_command") as mock_run:
            process_audio_pitch(input_file, output_file, pitch_factor)

        cmd = mock_run.call_args[0][0]
        af_value = cmd[cmd.index("-af") + 1]
        assert f"{expected_tempo:.6f}" in af_value

    def test_hz_ratio_pitch_factor_rubberband(self, tmp_path):
        """Using hz_ratio_to_pitch_factor result produces correct rubberband filter."""
        input_file = self._fake_file(tmp_path)
        output_file = tmp_path / "out.mp4"
        pitch_factor = hz_ratio_to_pitch_factor(450, 440)

        with patch("process_youtube_clip.has_rubberband", return_value=True), \
             patch("process_youtube_clip.run_command") as mock_run:
            process_audio_pitch(input_file, output_file, pitch_factor)

        cmd = mock_run.call_args[0][0]
        af_value = cmd[cmd.index("-af") + 1]
        assert f"{pitch_factor:.6f}" in af_value
