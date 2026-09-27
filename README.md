# Myanmar Recap Video Translator

Streamlit application for translating movie/drama recap videos into natural Myanmar Burmese narration with timestamped subtitles and a final MP4 export.

## Features

- Upload MP4, MOV, MKV, and WEBM videos
- FFmpeg audio extraction and media inspection
- Faster-Whisper automatic language detection and timestamped transcription
- Optional AssemblyAI transcription fallback via `ASSEMBLYAI_API_KEY`
- Gemini Flash translation using `GEMINI_API_KEY` (never hard-coded)
- Editable Burmese translations in a Streamlit table
- Real Burmese Edge TTS voices: Nilar and Thiha, with speed presets
- Timestamp-aware voice mixing; longer segments produce explicit timing warnings rather than being silently cut
- Burmese SRT export and subtitles burned into H.264/AAC MP4
- Downloads for original transcript, Burmese transcript, voice MP3, SRT, and final MP4

## Requirements

- Python 3.11+
- FFmpeg and FFprobe on PATH
- Enough RAM for the selected Whisper model (start with `base`)
- A Gemini API key for translation

## Run locally

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GEMINI_API_KEY
streamlit run app.py --server.address 0.0.0.0
```

Open `http://localhost:8501`. For Android access on the same network, open the host machine's port 8501 in the phone browser. On a cloud server, put HTTPS authentication/reverse proxy in front of Streamlit before exposing it publicly.

## Gemini model

The default is `gemini-3.8-flash`; set `GEMINI_MODEL` if your account uses a different current Gemini Flash model. The app uses JSON output to preserve segment order and timestamps.

## Voice note

Edge TTS does not provide eight distinct Myanmar voices. This project deliberately exposes only the two verified Myanmar voices and provides five rate presets, rather than making inaccurate voice claims.

## Deployment notes

This app is designed for a Linux cloud server with persistent disk because Whisper models, uploaded videos, generated audio, and final encodes can be large. Run behind a reverse proxy with TLS and authentication. Add a cleanup policy for `.work/` in production. For multiple users, replace session-local files with a job queue and object storage.

## Security

Never commit `.env` or API keys. The optional sidebar key is held only in the current Streamlit session and is not logged by the application.
