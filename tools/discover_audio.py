import pyaudiowpatch as pyaudio

def discover():
    p = pyaudio.PyAudio()
    try:
        # Znajdź host API WASAPI (wymagane dla Loopback na Windows)
        wasapi_info = None
        for i in range(p.get_host_api_count()):
            api_info = p.get_host_api_info_by_index(i)
            if api_info["name"].find("Windows WASAPI") != -1:
                wasapi_info = api_info
                break
        
        if not wasapi_info:
            print("[!] Błąd: Nie znaleziono Windows WASAPI API.")
            return

        print(f"[*] Host API: {wasapi_info['name']}")
        
        # Pobierz domyślne wyjście (głośniki/słuchawki)
        default_output = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        print(f"[*] Domyślne wyjście: {default_output['name']}")
        
        # Szukaj pasującego Loopbacka
        loopback_device = None
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi_info["index"] and dev["isLoopbackDevice"]:
                print(f"[+] Znaleziono Loopback: {dev['name']} (Index: {dev['index']})")
                loopback_device = dev
        
        if not loopback_device:
            print("[!] Nie znaleziono urządzenia Loopback.")
            
    finally:
        p.terminate()

if __name__ == "__main__":
    discover()
