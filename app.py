from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from utils.subtitles import segments_to_srt
from utils.transcription import TranscriptionError, transcribe_audio
from utils.translation import TranslationError, translate_segments
from utils.tts import SPEEDS, VOICES, VoiceError, generate_voice_preview, generate_voiceover
from utils.video import VideoError, export_final_video, extract_audio, get_media_info

load_dotenv()
st.set_page_config(page_title="Myanmar Recap Video Translator", page_icon="🎬", layout="wide")
WORK_ROOT = Path(".work")
WORK_ROOT.mkdir(exist_ok=True)


def init_state() -> None:
    defaults = {"job_dir": None, "video_path": None, "audio_path": None, "media_info": None, "segments": [], "translated": [], "voice_path": None, "srt_path": None, "final_video": None, "source_name": None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_job() -> None:
    for key in ("job_dir", "video_path", "audio_path", "media_info", "voice_path", "srt_path", "final_video", "source_name"):
        st.session_state[key] = None
    st.session_state.segments = []
    st.session_state.translated = []


def download(path: str | Path | None, label: str, mime: str) -> None:
    if path and Path(path).exists():
        p = Path(path)
        st.download_button(label, p.read_bytes(), file_name=p.name, mime=mime, use_container_width=True)


init_state()
st.title("Myanmar Recap Video Translator")
st.caption("ဗီဒီယိုကို စာသားထုတ်၊ မြန်မာဘာသာပြန်၊ မြန်မာအသံထည့်ပြီး subtitle ပါတဲ့ MP4 ထုတ်ပေးပါမယ်။")

with st.sidebar:
    st.header("ဆက်တင်များ")
    api_key_input = st.text_input("Gemini API key (ရွေးချယ်နိုင်)", type="password", help="GEMINI_API_KEY ကို ဦးစားပေးအသုံးပြုပါသည်။ Key ကို မပြသ၊ မမှတ်တမ်းတင်ပါ။")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    whisper_model = st.selectbox("Whisper model", ["tiny", "base", "small", "medium", "large-v3"], index=1)
    voice_name = st.selectbox("မြန်မာအသံ", list(VOICES), format_func=lambda x: VOICES[x]["label"])
    speed = st.selectbox("အသံအမြန်နှုန်း", SPEEDS, format_func=lambda x: f"{x:.2f}x")
    with st.expander("အသံတစ်မျိုးချင်းစီ နားထောင်ရန်"):
        st.caption("အသံ ၂ မျိုးသာ အမှန်တကယ်ရရှိပါတယ်။ ရွေးမချယ်မီ နမူနာနားထောင်ပါ။")
        for preview_voice, metadata in VOICES.items():
            st.write(metadata["label"])
            preview_path = st.session_state.get(f"preview_{preview_voice}")
            if st.button("▶ နားထောင်ရန်", key=f"preview_button_{preview_voice}", use_container_width=True):
                try:
                    preview_path = generate_voice_preview(preview_voice, WORK_ROOT / f"preview_{preview_voice}.mp3")
                    st.session_state[f"preview_{preview_voice}"] = str(preview_path)
                except VoiceError as exc:
                    st.error(str(exc))
            if preview_path and Path(preview_path).exists():
                st.audio(preview_path, format="audio/mp3")
    if st.button("အလုပ်အသစ်စပါ", use_container_width=True):
        reset_job()
        st.rerun()
    st.info("Edge TTS မှာ တကယ်ရရှိနိုင်တဲ့ မြန်မာအသံ ၂ မျိုးကိုသာ ပြထားပါတယ်။ အခြားရွေးချယ်စရာတွေက speed preset များ ဖြစ်ပါတယ်။")

uploaded = st.file_uploader("STEP 1 — ဗီဒီယိုတင်ရန်", type=["mp4", "mov", "mkv", "webm"])
if uploaded is not None and st.session_state.source_name != uploaded.name:
    reset_job()
    safe_name = Path(uploaded.name).name
    job_dir = WORK_ROOT / safe_name.rsplit(".", 1)[0][:60]
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / safe_name
    video_path.write_bytes(uploaded.getbuffer())
    st.session_state.update(job_dir=job_dir, video_path=video_path, source_name=uploaded.name)
    try:
        st.session_state.media_info = get_media_info(video_path)
    except VideoError as exc:
        st.error(str(exc))

if not st.session_state.video_path:
    st.info("စတင်ရန် ဗီဒီယိုတစ်ခု တင်ပါ။")
    st.stop()

info = st.session_state.media_info or {}
col1, col2 = st.columns([1, 2])
with col1:
    st.metric("ကြာချိန်", f"{info.get('duration', 0):.1f}s")
    st.metric("Resolution", f"{info.get('width', '?')} × {info.get('height', '?')}")
    st.metric("အသံ", "ရှိသည်" if info.get("has_audio") else "မရှိပါ")
with col2:
    st.video(str(st.session_state.video_path))
if not info.get("has_audio"):
    st.error("ဤဗီဒီယိုတွင် audio stream မရှိပါ။ အသံပါသောဗီဒီယိုကို တင်ပါ။")
    st.stop()

if st.button("STEP 2 — Audio ထုတ်ပြီး စာသားဖော်ရန်", type="primary", use_container_width=True):
    try:
        with st.status("Audio ထုတ်ပြီး transcription လုပ်နေပါသည်…", expanded=True) as status:
            audio_path = st.session_state.job_dir / "original_audio.wav"
            extract_audio(st.session_state.video_path, audio_path)
            st.session_state.audio_path = audio_path
            segments, language = transcribe_audio(audio_path, model_size=whisper_model)
            st.session_state.segments = segments
            status.update(label=f"Transcription ပြီးပါပြီ ({language})", state="complete")
    except (VideoError, TranscriptionError) as exc:
        st.error(str(exc))

if st.session_state.segments:
    st.subheader("STEP 3 — မူရင်း Transcription")
    st.dataframe(pd.DataFrame(st.session_state.segments), use_container_width=True, hide_index=True)
    if st.button("STEP 4 — Gemini ဖြင့် မြန်မာဘာသာပြန်ရန်", use_container_width=True):
        api_key = api_key_input or os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("Sidebar တွင် key ထည့်ပါ သို့မဟုတ် GEMINI_API_KEY environment variable သတ်မှတ်ပါ။")
        else:
            try:
                with st.spinner("Gemini ဖြင့် သဘာဝကျသော မြန်မာဘာသာပြန်နေပါသည်…"):
                    st.session_state.translated = translate_segments(st.session_state.segments, api_key, model_name)
            except TranslationError as exc:
                st.error(str(exc))

if st.session_state.translated:
    st.subheader("STEP 5 — ဘာသာပြန်စာကို ပြင်ရန်")
    edited = st.data_editor(pd.DataFrame(st.session_state.translated), use_container_width=True, hide_index=True, num_rows="fixed", column_config={"start": st.column_config.NumberColumn("အစ (စက္ကန့်)", disabled=True), "end": st.column_config.NumberColumn("အဆုံး (စက္ကန့်)", disabled=True), "original": st.column_config.TextColumn("မူရင်း", disabled=True), "burmese": st.column_config.TextColumn("မြန်မာဘာသာပြန်")})
    st.session_state.translated = edited.to_dict("records")
    job = st.session_state.job_dir
    original_txt = job / "original_transcript.txt"
    original_txt.write_text("\n".join(f"[{s['start']:.2f}–{s['end']:.2f}] {s['original']}" for s in st.session_state.segments), encoding="utf-8")
    burmese_txt = job / "burmese_transcript.txt"
    burmese_txt.write_text("\n".join(f"[{s['start']:.2f}–{s['end']:.2f}] {s['burmese']}" for s in st.session_state.translated), encoding="utf-8")

    st.subheader("STEP 6 — မြန်မာအသံဖန်တီးရန်")
    if st.button("Burmese voice-over ဖန်တီးရန်", use_container_width=True):
        try:
            with st.status("မြန်မာအသံဖန်တီးပြီး timestamp နှင့်ချိန်ညှိနေပါသည်…", expanded=True) as status:
                voice_path, warnings = generate_voiceover(st.session_state.translated, job / "burmese_voice.mp3", voice_name, speed)
                st.session_state.voice_path = voice_path
                for warning in warnings:
                    st.warning(warning)
                status.update(label="Voice-over ပြီးပါပြီ", state="complete")
        except VoiceError as exc:
            st.error(str(exc))

    st.subheader("STEP 7 — Burmese SRT ဖန်တီးရန်")
    if st.button("Burmese SRT ဖန်တီးရန်", use_container_width=True):
        srt_path = job / "burmese_subtitles.srt"
        srt_path.write_text(segments_to_srt(st.session_state.translated), encoding="utf-8")
        st.session_state.srt_path = srt_path
    download(st.session_state.srt_path, "Burmese SRT ဒေါင်းလုပ်", "application/x-subrip")

    st.subheader("STEP 8 — Final MP4 ထုတ်ရန်")
    with st.expander("Final video ပြင်ဆင်မှုများ", expanded=True):
        burn_subtitles = st.checkbox("မြန်မာစာတန်းထိုး ထည့်ရန်", value=True)
        subtitle_size = st.slider("မြန်မာစာတန်း အရွယ်", 12, 72, 32) if burn_subtitles else 32
        subtitle_color = st.color_picker("မြန်မာစာတန်း အရောင်", "#FFFFFF") if burn_subtitles else "#FFFFFF"
        blur_video = st.checkbox("Video blur လုပ်ရန်", value=False)
        blur_strength = st.slider("Blur အား", 1, 8, 2) if blur_video else 2
        logo_text = st.text_input("ကိုယ်ပိုင် logo စာတန်း (ရွေးချယ်နိုင်)", placeholder="ဥပမာ - My Channel")
        logo_size = st.slider("Logo စာလုံးအရွယ်", 12, 96, 28)
        logo_opacity = st.slider("Logo မှိန်မှု", 0.05, 0.60, 0.18, 0.01, help="နည်းလေလေ ပိုမှိန်လေလေ ဖြစ်ပါတယ်။")
        logo_period = st.slider("Logo အပေါ်အောက် ရွေ့ချိန် (စက္ကန့်)", 8, 60, 24, help="တစ်ကြိမ် အပေါ်မှအောက်သို့ ဖြည်းဖြည်းရွေ့ပြီး ပြန်လည်ရွေ့မည့် အချိန်။")
    if st.button("Final MP4 ထုတ်ရန်", type="primary", use_container_width=True):
        if not st.session_state.voice_path:
            st.error("အရင်ဆုံး Burmese voice-over ဖန်တီးပါ။")
        else:
            try:
                with st.spinner("Video၊ subtitle၊ watermark နှင့် audio encode လုပ်နေပါသည်…"):
                    srt_path = st.session_state.srt_path or job / "burmese_subtitles.srt"
                    srt_path.write_text(segments_to_srt(st.session_state.translated), encoding="utf-8")
                    st.session_state.srt_path = srt_path
                    st.session_state.final_video = export_final_video(st.session_state.video_path, st.session_state.voice_path, srt_path, job / "myanmar_recap_burmese.mp4", burn_subtitles=burn_subtitles, blur_video=blur_video, blur_strength=blur_strength, subtitle_size=subtitle_size, subtitle_color=subtitle_color, logo_text=logo_text, logo_size=logo_size, logo_opacity=logo_opacity, logo_period=logo_period)
            except VideoError as exc:
                st.error(str(exc))
    download(st.session_state.final_video, "Final MP4 ဒေါင်းလုပ်", "video/mp4")

    st.divider()
    st.subheader("Downloads")
    c1, c2 = st.columns(2)
    with c1:
        download(original_txt, "Original transcript TXT", "text/plain")
        download(burmese_txt, "Burmese transcript TXT", "text/plain")
    with c2:
        download(st.session_state.voice_path, "Burmese voice MP3", "audio/mpeg")
        download(st.session_state.final_video, "Final MP4", "video/mp4")
