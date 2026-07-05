@echo off
TITLE Gemma-4 Sovereign Server
cd /d "C:\Users\gamin\Desktop\mat\llama_cpp"
echo [STARTING] Gemma-4 Server on GPU (RTX 5050)...
echo [INFO] API will be available at http://localhost:8080/v1
llama-server.exe -m "C:\Users\gamin\Desktop\mat\models\gemma-4-9b-q4.gguf" -ngl 99 --port 8080 --host 127.0.0.1
pause
