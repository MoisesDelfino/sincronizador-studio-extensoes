@echo off
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo Python nao encontrado. Instalando via winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo Concluido. Feche esta janela e abra o Studio Sync novamente.
  pause
  exit /b
)
if exist ".preparado" (
  start "" /b %PY% iniciar.py
) else (
  %PY% iniciar.py
)
