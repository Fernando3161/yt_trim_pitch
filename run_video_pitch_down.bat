@echo off
setlocal

set VIDEO_URL=https://www.youtube.com/watch?v=jHfQCfUTlXE
set START_TIME=00:00:00
set END_TIME=00:02:00
set OUTPUT_FILE=clip_medio_tono_abajo.mp4

python process_youtube_clip.py "%VIDEO_URL%" --start %START_TIME% --end %END_TIME% --output "%OUTPUT_FILE%"

endlocal
