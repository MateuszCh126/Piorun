import numpy as np

import tools.lecture_recorder as lr


# --- compute_rms (czysta funkcja) ------------------------------------------

def test_compute_rms_silence_is_zero():
    silence = np.zeros(lr.CHUNK_SIZE, dtype=np.int16).tobytes()
    assert lr.compute_rms(silence) == 0.0


def test_compute_rms_empty_is_zero():
    assert lr.compute_rms(b"") == 0.0


def test_compute_rms_loud_is_high():
    loud = (np.ones(lr.CHUNK_SIZE) * 10000).astype(np.int16).tobytes()
    assert lr.compute_rms(loud) > 5000


# --- detekcja ciszy ---------------------------------------------------------

def _recorder():
    rec = lr.LectureRecorder("Test")
    rec.rate = 16000
    return rec


def test_silence_warning_triggers_after_threshold(monkeypatch, capsys):
    monkeypatch.setattr(lr, "SILENCE_WARN_SECONDS", 0.2)  # ~4 chunki przy 16 kHz
    rec = _recorder()
    silence = np.zeros(lr.CHUNK_SIZE, dtype=np.int16).tobytes()
    for _ in range(20):
        rec._track_silence(silence)
    assert rec.silence_warned is True
    assert rec.max_silence_seconds > 0.2
    assert "cisza" in capsys.readouterr().out.lower()


def test_sound_resets_silence(monkeypatch):
    monkeypatch.setattr(lr, "SILENCE_WARN_SECONDS", 0.2)
    rec = _recorder()
    silence = np.zeros(lr.CHUNK_SIZE, dtype=np.int16).tobytes()
    loud = (np.ones(lr.CHUNK_SIZE) * 10000).astype(np.int16).tobytes()
    for _ in range(10):
        rec._track_silence(silence)
    assert rec.silent_seconds > 0
    rec._track_silence(loud)
    assert rec.silent_seconds == 0.0
    assert rec.silence_warned is False


# --- fallback urzadzenia loopback ------------------------------------------

class FakePyAudio:
    def __init__(self, devices, default_output_index):
        self._devices = devices
        self._default_output = default_output_index

    def get_host_api_count(self):
        return 1

    def get_host_api_info_by_index(self, i):
        return {"name": "Windows WASAPI", "index": 0, "defaultOutputDevice": self._default_output}

    def get_device_count(self):
        return len(self._devices)

    def get_device_info_by_index(self, i):
        return self._devices[i]


def _dev(index, name, loopback):
    return {"index": index, "name": name, "hostApi": 0, "isLoopbackDevice": loopback}


def test_loopback_prefers_default_output_match():
    devices = [
        _dev(0, "Speakers", False),
        _dev(1, "Speakers [Loopback]", True),
        _dev(2, "Headphones [Loopback]", True),
    ]
    dev = lr.LectureRecorder("T").get_loopback_device(FakePyAudio(devices, default_output_index=0))
    assert dev["name"] == "Speakers [Loopback]"


def test_loopback_falls_back_to_first_available(capsys):
    devices = [
        _dev(0, "Monitor Output", False),  # default output bez pasujacego loopbacku
        _dev(1, "Headphones [Loopback]", True),
    ]
    dev = lr.LectureRecorder("T").get_loopback_device(FakePyAudio(devices, default_output_index=0))
    assert dev["name"] == "Headphones [Loopback]"
    assert "uzywam" in capsys.readouterr().out.lower()


def test_loopback_none_when_no_loopback():
    devices = [_dev(0, "Speakers", False)]
    dev = lr.LectureRecorder("T").get_loopback_device(FakePyAudio(devices, default_output_index=0))
    assert dev is None
