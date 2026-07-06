import hashlib
import json
import os
import threading
import time
import wave
from datetime import datetime

import mss
import pyaudiowpatch as pyaudio
from PIL import Image

try:
    from core.config import get_settings
except ModuleNotFoundError:
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings


SETTINGS = get_settings()
OUTPUT_BASE = str(SETTINGS.sessions_root)
SCREENSHOT_INTERVAL = int(os.environ.get("PIORUN_LECTURE_SCREENSHOT_INTERVAL_SECONDS", "30"))
SCREENSHOT_MAX_WIDTH = int(os.environ.get("PIORUN_LECTURE_SCREENSHOT_MAX_WIDTH", "1600"))
SCREENSHOT_JPEG_QUALITY = int(os.environ.get("PIORUN_LECTURE_SCREENSHOT_JPEG_QUALITY", "72"))
SCREENSHOT_HASH_DOWNSCALE = (320, 180)
CHANNELS = int(os.environ.get("PIORUN_LECTURE_AUDIO_CHANNELS", "2"))
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16


class LectureRecorder:
    def __init__(self, subject):
        self.subject = subject
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        safe_subject = "".join(c if c.isalnum() or c in "-_ " else "_" for c in subject).strip() or "Wyklad"
        self.session_dir = os.path.join(OUTPUT_BASE, f"{self.timestamp}_{safe_subject}")
        self.slides_dir = os.path.join(self.session_dir, "slides")
        self.audio_path = os.path.join(self.session_dir, "audio.wav")
        self.timeline_path = os.path.join(self.session_dir, "slides_timeline.json")
        self.metadata_path = os.path.join(self.session_dir, "session_meta.json")

        self.recording = False
        self.timeline = []
        self.last_slide_hash = None
        self.start_time = None
        self.slide_index = 0
        self.active_channels = CHANNELS
        self.wave_writer = None
        self.frames_written = 0
        self.audio_errors = 0

    def get_loopback_device(self, p):
        wasapi_info = None
        for i in range(p.get_host_api_count()):
            api_info = p.get_host_api_info_by_index(i)
            if "WASAPI" in api_info["name"]:
                wasapi_info = api_info
                break

        if not wasapi_info:
            return None

        default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi_info["index"] and dev.get("isLoopbackDevice"):
                if default_output["name"] in dev["name"]:
                    return dev
        return None

    def _open_stream(self, dev):
        candidates = [CHANNELS, 1, 2]
        tried = set()
        for channels in candidates:
            if channels in tried:
                continue
            tried.add(channels)
            try:
                stream = self.p.open(
                    format=FORMAT,
                    channels=channels,
                    rate=self.rate,
                    input=True,
                    input_device_index=dev["index"],
                    frames_per_buffer=CHUNK_SIZE,
                )
                self.active_channels = channels
                return stream
            except Exception:
                continue
        return None

    def _init_wave_writer(self):
        self.wave_writer = wave.open(self.audio_path, "wb")
        self.wave_writer.setnchannels(self.active_channels)
        self.wave_writer.setsampwidth(self.p.get_sample_size(FORMAT))
        self.wave_writer.setframerate(self.rate)

    def _write_metadata(self):
        payload = {
            "subject": self.subject,
            "created_at": datetime.now().isoformat(),
            "sample_rate": self.rate,
            "channels": self.active_channels,
            "chunk_size": CHUNK_SIZE,
            "screenshot_interval_seconds": SCREENSHOT_INTERVAL,
            "screenshot_max_width": SCREENSHOT_MAX_WIDTH,
            "screenshot_jpeg_quality": SCREENSHOT_JPEG_QUALITY,
        }
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def start(self):
        os.makedirs(self.slides_dir, exist_ok=True)
        self.p = pyaudio.PyAudio()

        dev = self.get_loopback_device(self.p)
        if not dev:
            print("[!] Blad: Nie znaleziono urzadzenia Loopback.")
            return False

        self.rate = int(dev["defaultSampleRate"])
        self.stream = self._open_stream(dev)
        if not self.stream:
            print("[!] Blad: Nie udalo sie otworzyc streamu loopback.")
            self.p.terminate()
            return False

        self._init_wave_writer()
        self._write_metadata()

        # Sonda: jeden odczyt na starcie, zeby nie odkryc po wykladzie, ze stream byl martwy.
        try:
            probe = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            self.wave_writer.writeframesraw(probe)
            self.frames_written += 1
        except Exception as e:
            print(f"[!] Blad: strumien loopback nie dostarcza audio: {e}")
            self.stream.close()
            self.wave_writer.close()
            self.wave_writer = None
            self.p.terminate()
            return False

        print(f"[*] Nagrywanie z: {dev['name']} ({self.rate} Hz, {self.active_channels} kanal(y))")

        self.recording = True
        self.start_time = time.time()

        self.audio_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.slide_thread = threading.Thread(target=self._monitor_slides, daemon=True)
        self.audio_thread.start()
        self.slide_thread.start()
        return True

    def stop(self):
        self.recording = False
        self.audio_thread.join(timeout=10)
        self.slide_thread.join(timeout=max(10, SCREENSHOT_INTERVAL + 5))

        self.stream.stop_stream()
        self.stream.close()
        if self.wave_writer:
            self.wave_writer.close()
            self.wave_writer = None
        self.p.terminate()

        with open(self.timeline_path, "w", encoding="utf-8") as f:
            json.dump(self.timeline, f, ensure_ascii=False, indent=2)

        duration = self.frames_written * CHUNK_SIZE / float(self.rate or 1)
        if self.frames_written <= 1:
            print("[!] UWAGA: audio.wav jest praktycznie puste - nagrywanie audio NIE powiodlo sie.")
        else:
            print(
                f"[*] Audio: ~{duration:.0f}s zapisane ({self.frames_written} fragmentow, "
                f"bledy odczytu: {self.audio_errors})."
            )
        return self.session_dir

    def _record_audio(self):
        frames_since_flush = 0
        while self.recording:
            try:
                data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if self.wave_writer:
                    self.wave_writer.writeframesraw(data)
                    self.frames_written += 1
                    frames_since_flush += 1
                    # Okresowy flush: przy padzie procesu na dysku zostaje dotychczasowe audio.
                    if frames_since_flush >= 200:
                        frames_since_flush = 0
                        try:
                            self.wave_writer._file.flush()
                        except Exception:
                            pass
            except Exception as e:
                self.audio_errors += 1
                if self.audio_errors <= 3:
                    print(f"[!] Blad odczytu audio (#{self.audio_errors}): {e}")
                time.sleep(0.05)

    def _hash_image(self, img):
        small = img.convert("L").resize(SCREENSHOT_HASH_DOWNSCALE, Image.Resampling.BILINEAR)
        return hashlib.md5(small.tobytes()).hexdigest()

    def _save_slide(self, img, elapsed):
        if SCREENSHOT_MAX_WIDTH > 0 and img.width > SCREENSHOT_MAX_WIDTH:
            ratio = SCREENSHOT_MAX_WIDTH / float(img.width)
            new_size = (SCREENSHOT_MAX_WIDTH, max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        self.slide_index += 1
        filename = f"slide_{self.slide_index:04d}_{elapsed}s.jpg"
        filepath = os.path.join(self.slides_dir, filename)
        img.save(filepath, "JPEG", quality=max(25, min(95, SCREENSHOT_JPEG_QUALITY)), optimize=True)

        self.timeline.append({"timestamp": elapsed, "file": f"slides/{filename}"})
        print(f"[*] Wykryto nowy slajd w {elapsed}s")

    def _monitor_slides(self):
        with mss.mss() as sct:
            while self.recording:
                elapsed = int(time.time() - self.start_time)
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                current_hash = self._hash_image(img)

                if current_hash != self.last_slide_hash:
                    self._save_slide(img, elapsed)
                    self.last_slide_hash = current_hash
                time.sleep(SCREENSHOT_INTERVAL)


if __name__ == "__main__":
    import sys

    subject = sys.argv[1] if len(sys.argv) > 1 else "Wyklad"
    rec = LectureRecorder(subject)
    if rec.start():
        print(f"\n[PIORUN REC] Sesja: {subject} AKTYWNA.")
        print("Wcisnij Ctrl+C aby zakonczyc i zapisac...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            path = rec.stop()
            print(f"\n[OK] Sesja zapisana: {path}")
