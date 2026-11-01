@echo off
setlocal
set "ROOT=%~dp0"
if /I "%~1"=="--smoke" (
  set QT_QPA_PLATFORM=offscreen
  set NUMBA_NUM_THREADS=1
  set PYTHONNOUSERSITE=1
  set QT_API=pyside6
  "%ROOT%runtime\python.exe" "%ROOT%smoke_check.py"
  exit /b %ERRORLEVEL%
)
cscript //nologo "%ROOT%Spektrafilm.vbs"
exit /b 0
