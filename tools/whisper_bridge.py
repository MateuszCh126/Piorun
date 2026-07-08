from faster_whisper import WhisperModel
import json
import os
import gc
import time
import wave
import numpy as np
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

# KONFIGURACJA
# Ścieżka do ręcznie pobranego modelu (folder z plikami .bin, config.json itd.)
SETTINGS = get_settings()
MODEL_PATH = str(SETTINGS.whisper_model_path)
MODEL_SIZE = os.path.basename(MODEL_PATH)
TARGET_RATE = 16000  # Whisper wymaga 16kHz

def resample_audio(audio_path):
    """Konwertuje WAV (48kHz Stereo) na 16kHz Mono dla Whispera."""
    resampled_path = audio_path.replace(".wav", "_16k.wav")
    
    try:
        from scipy.signal import resample_poly
        from math import gcd
        
        with wave.open(audio_path, 'rb') as wf:
            channels = wf.getnchannels()
            orig_rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        
        # Konwersja bajtów na numpy array
        audio = np.frombuffer(frames, dtype=np.int16)
        
        # Stereo -> Mono (uśrednienie kanałów)
        if channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)
        
        # Resampling do 16kHz
        if orig_rate != TARGET_RATE:
            g = gcd(orig_rate, TARGET_RATE)
            audio = resample_poly(audio, TARGET_RATE // g, orig_rate // g)
            audio = audio.astype(np.int16)
        
        # Zapisz jako nowy WAV
        with wave.open(resampled_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_RATE)
            wf.writeframes(audio.tobytes())
        
        print(f"[*] Audio przekonwertowane: {orig_rate}Hz {channels}ch -> {TARGET_RATE}Hz Mono")
        return resampled_path
    except ImportError:
        print("[!] scipy niedostępne, używam oryginalnego pliku (może być gorsza jakość)")
        return audio_path
    except Exception as e:
        print(f"[!] Błąd konwersji audio: {e}, używam oryginału")
        return audio_path

def transcribe_session(session_dir):
    audio_path = os.path.join(session_dir, "audio.wav")
    if not os.path.exists(audio_path):
        # Fallback na formaty skompresowane, jesli pojawia sie w przyszlosci.
        for alt in ("audio.flac", "audio.mp3", "audio.m4a", "audio.opus"):
            alt_path = os.path.join(session_dir, alt)
            if os.path.exists(alt_path):
                audio_path = alt_path
                break
    output_path = os.path.join(session_dir, "transcript.json")
    
    if not os.path.exists(audio_path):
        return f"Błąd: Plik audio nie istnieje w {session_dir}"

    # Konwersja audio do formatu Whisper (16kHz Mono)
    audio_ready = resample_audio(audio_path)

    print(f"[*] Ładowanie modelu Whisper ({MODEL_SIZE})...")
    start_time = time.time()
    
    try:
        model = WhisperModel(MODEL_PATH, device="cuda", compute_type="float16")
    except Exception as e:
        print(f"[!] Błąd CUDA, próba ładowania na CPU: {e}")
        model = WhisperModel(MODEL_PATH, device="cpu", compute_type="int8")

    print("[*] Rozpoczynanie transkrypcji...")
    # Podpowiedz jezyka: przy cichym poczatku Whisper czasem myli detekcje.
    language = os.environ.get("PIORUN_LECTURE_LANGUAGE", "").strip() or None
    segments, info = model.transcribe(audio_ready, beam_size=5, language=language)
    
    results = []
    print(f"[*] Wykryto język: {info.language} (Prawdop: {info.language_probability:.2f})")

    for segment in segments:
        results.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip()
        })
        # Wyświetlaj postęp w konsoli
        timestamp = time.strftime('%H:%M:%S', time.gmtime(segment.start))
        print(f"[{timestamp}] {segment.text.strip()}")

    # Zapisz do JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    exec_time = time.time() - start_time
    print(f"\n[OK] Transkrypcja ukończona w {exec_time:.1f}s. Wynik: {output_path}")

    # CZYSZCZENIE VRAM
    del model
    gc.collect()
    # Jeśli mamy pycatche lub inne bufory
    try:
        import torch
        torch.cuda.empty_cache()
    except:
        pass

    # Sprzatanie pliku pomocniczego (audio_16k.wav)
    if audio_ready != audio_path and audio_ready.endswith("_16k.wav") and os.path.exists(audio_ready):
        try:
            os.remove(audio_ready)
        except Exception:
            pass

    return output_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Użycie: python whisper_bridge.py [ścieżka_do_sesji]")
    else:
        transcribe_session(sys.argv[1])
