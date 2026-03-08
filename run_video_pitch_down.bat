@echo off
setlocal

set VIDEO_URL=https://www.youtube.com/watch?v=jHfQCfUTlXE
set START_TIME=00:00:00
set END_TIME=00:02:00
set OUTPUT_FILE=clip_medio_tono_abajo.mp4

rem Pitch shift options — pick ONE of the two methods below and comment out the other.
rem
rem Method 1: semitones  (negative = down, positive = up)
rem   --semitones -1     lowers by one semitone (default)
rem   --semitones +3     raises by three semitones
rem
rem Method 2: Hz ratio   (set the pitch detected in the video and the desired pitch)
rem   --ref-hz 450 --target-hz 440
rem
rem Default: -1 semitone (one semitone down)
set PITCH_ARGS=--semitones -1

python process_youtube_clip.py "%VIDEO_URL%" --start %START_TIME% --end %END_TIME% --output "%OUTPUT_FILE%" %PITCH_ARGS%

endlocal
