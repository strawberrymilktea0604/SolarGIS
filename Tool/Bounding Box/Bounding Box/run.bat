@echo off
title OrthoScope BBox Web Application
cd /d "%~dp0"
echo ========================================================
echo   OrthoScope BBox - Web Doc Ortho & Bounding Box Vung
echo ========================================================
echo Dang khoi dong Web Server tren http://127.0.0.1:8000 ...
start http://127.0.0.1:8000
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
