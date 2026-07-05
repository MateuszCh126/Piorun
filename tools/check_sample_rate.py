import pyaudiowpatch as pyaudio

def check_rate():
    p = pyaudio.PyAudio()
    try:
        wasapi_info = None
        for i in range(p.get_host_api_count()):
            if "WASAPI" in p.get_host_api_info_by_index(i)["name"]:
                wasapi_info = p.get_host_api_info_by_index(i)
                break
        
        if wasapi_info:
            default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            print(f"[*] Urzadzenie: {default_output['name']}")
            print(f"[*] Natywny Sample Rate: {int(default_output['defaultSampleRate'])} Hz")
            
    finally:
        p.terminate()

if __name__ == "__main__":
    check_rate()
