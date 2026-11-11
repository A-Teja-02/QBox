@echo off
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0connect_db.ps1" %*

