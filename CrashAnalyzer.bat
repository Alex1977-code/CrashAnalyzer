@echo off
rem Crash Analyzer - Doppelklick-Start
title Crash Analyzer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\run.ps1"
if errorlevel 1 pause
