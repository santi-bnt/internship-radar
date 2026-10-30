@echo off
title Internship Radar - Local HTML and Vision Assistant
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local-assistant.ps1" -WithDockerVision
if errorlevel 1 pause
