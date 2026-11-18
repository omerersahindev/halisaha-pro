@echo off
cd /d "%~dp0"
start "" "http://127.0.0.1:8000"
uvicorn app:app --reload --host 0.0.0.0 --port 8000
