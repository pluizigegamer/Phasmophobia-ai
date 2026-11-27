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
    # Resize to 720p to save VRAM and speed up inference
    resized = cv2.resize(frame, (1280, 720))
    _, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buffer).decode('utf-8')

def analyze_footstep_speed(audio_data, sample_rate=22050):
    """Estimates ghost speed based on audio transient peaks (footsteps)."""
    # Filter low-end thuds (footsteps are mostly 40Hz - 250Hz)
    onset_env = librosa.onset.onset_strength(y=audio_data, sr=sample_rate)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sample_rate)
    bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    
    # Standard Phasmophobia ghost speed is ~1.7 m/s (~115 BPM footsteps)
    if bpm < 95:
        return f"Slow (~{int(bpm)} BPM) - Possible Revenant/Deogen/Thaye(old)"
    elif 95 <= bpm <= 130:
        return f"Normal (~{int(bpm)} BPM)"
    elif bpm > 130:
        return f"Fast (~{int(bpm)} BPM) - Possible Rev/Raiju/Hantu/Moroi/Thaye"
    return "No footsteps detected"

def record_and_analyze(clip_duration=15, callback=None):
    """Records screen + audio for X seconds, analyzes, and deletes if nothing happened."""
    os.makedirs("clips", exist_ok=True)
    timestamp = int(time.time())
    video_path = f"clips/clip_{timestamp}.avi"
    
    sample_rate = 22050
    fps = 10
    
    # Start non-blocking audio recording
    audio_recording = sd.rec(int(clip_duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    
    key_frames_b64 = []
    
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(video_path, fourcc, fps, (monitor["width"], monitor["height"]))
        
        total_frames = clip_duration * fps
        for i in range(total_frames):
            loop_start = time.time()
            img = np.array(sct.grab(monitor))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            out.write(frame)
            
            # Grab 1 keyframe every 3 seconds for the AI
            if i % (fps * 3) == 0:
                key_frames_b64.append(encode_frame(frame))
                
            elapsed = time.time() - loop_start
            if elapsed < (1.0 / fps):
                time.sleep((1.0 / fps) - elapsed)
                
        out.release()
    sd.wait()

    # Check if audio had loud activity (hunts/events)
    audio_flat = audio_recording.flatten()
    max_volume = np.max(np.abs(audio_flat))
    speed_analysis = analyze_footstep_speed(audio_flat, sample_rate) if max_volume > 0.15 else "Quiet"

    # Prompt the local Vision LLM
    prompt = (
        "You are analyzing 5 sequential screenshots from the game Phasmophobia taken over 15 seconds. "
        "Look closely for ghost activity: Did a room light turn ON or OFF? Did a door move? "
        "Is a ghost visible, hunting (flashing flashlight/screen distortion), or are DOTS/Ghost Orbs visible? "
        "If NOTHING paranormal or notable happened (just walking around normally), reply ONLY with the word: NOTHING. "
        "Otherwise, briefly list the exact events in 1-2 short bullet points."
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "images": key_frames_b64,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        ai_result = response.json().get("response", "NOTHING").strip()
    except Exception as e:
        ai_result = f"AI Error: {e}"

    # Delete footage if nothing happened
    if "NOTHING" in ai_result.upper() and speed_analysis == "Quiet":
        if os.path.exists(video_path):
            os.remove(video_path)
        if callback:
            callback(f"[{time.strftime('%H:%M:%S')}] Idle - Clip deleted.")
    else:
        log_msg = f"[{time.strftime('%H:%M:%S')}] SAVED ({video_path})\nAudio: {speed_analysis}\nVisual: {ai_result}\n"
        if callback:
            callback(log_msg)