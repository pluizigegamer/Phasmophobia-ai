import os
import time
import base64
import cv2
import mss
import numpy as np
import requests
import sounddevice as sd
import librosa

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5vl:7b"


def encode_frame(frame):
    # 960x540 keeps visual detail for lights/ghosts while cutting VLM token/compute load
    resized = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
    _, buffer = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 65])
    return base64.b64encode(buffer).decode("utf-8")


def analyze_footstep_speed(audio_data, sample_rate=22050):
    """Estimates footstep cadence only when clear rhythmic audio is present."""
    rms = float(np.sqrt(np.mean(np.square(audio_data))))
    if rms < 0.04:
        return "Quiet"

    onset_env = librosa.onset.onset_strength(y=audio_data, sr=sample_rate)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sample_rate)
    bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)

    # Filter out obviously non-footstep noise spikes
    if bpm < 55 or bpm > 195:
        return f"Audio activity (~{int(bpm)} BPM raw - verify hunt footsteps)"

    if bpm < 95:
        return f"Slow (~{int(bpm)} BPM) - Possible Revenant/Deogen/Thaye(old)"
    elif 95 <= bpm <= 130:
        return f"Normal (~{int(bpm)} BPM)"
    else:
        return f"Fast (~{int(bpm)} BPM) - Possible Fast/LOS/Low-Sanity/Rev"


def record_and_analyze(clip_duration=15, callback=None):
    """Records screen + audio for clip_duration seconds, analyzes, and deletes if idle."""
    os.makedirs("clips", exist_ok=True)
    timestamp = int(time.time())
    video_path = f"clips/clip_{timestamp}.avi"

    sample_rate = 22050
    fps = 10

    audio_recording = sd.rec(
        int(clip_duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )

    key_frames_b64 = []
    # Grab 3 evenly spaced frames across the clip (start, middle, near-end)
    sample_indices = {
        0,
        max(1, (clip_duration * fps) // 2),
        max(2, (clip_duration * fps) - fps),
    }

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        out = cv2.VideoWriter(video_path, fourcc, fps, (monitor["width"], monitor["height"]))

        total_frames = clip_duration * fps
        for i in range(total_frames):
            loop_start = time.time()
            img = np.array(sct.grab(monitor))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            out.write(frame)

            if i in sample_indices:
                key_frames_b64.append(encode_frame(frame))

            elapsed = time.time() - loop_start
            if elapsed < (1.0 / fps):
                time.sleep((1.0 / fps) - elapsed)

        out.release()
    sd.wait()

    audio_flat = audio_recording.flatten()
    speed_analysis = analyze_footstep_speed(audio_flat, sample_rate)

    prompt = (
        "You are analyzing 3 sequential screenshots from Phasmophobia over 15 seconds. "
        "Check only for clear paranormal events: light turned ON/OFF or bulb burst, door moved/closed, "
        "ghost visible, hunt (flashlight flicker/distortion), or D.O.T.S/ghost activity. "
        "If nothing notable happened, reply ONLY with: NOTHING. "
        "Otherwise write 1-2 short bullet points."
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": key_frames_b64,
        "stream": False,
        "options": {
            "num_predict": 90,
            "temperature": 0.1,
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90)
        response.raise_for_status()
        ai_result = response.json().get("response", "NOTHING").strip()
    except Exception as e:
        ai_result = f"AI Error: {e}"

    is_nothing = ai_result.upper().startswith("NOTHING")
    if is_nothing and speed_analysis == "Quiet":
        if os.path.exists(video_path):
            os.remove(video_path)
        if callback:
            callback(f"[{time.strftime('%H:%M:%S')}] Idle - Clip deleted.")
    else:
        log_msg = (
            f"[{time.strftime('%H:%M:%S')}] SAVED ({video_path})\n"
            f"Audio: {speed_analysis}\n"
            f"Visual: {ai_result}\n"
        )
        if callback:
            callback(log_msg)