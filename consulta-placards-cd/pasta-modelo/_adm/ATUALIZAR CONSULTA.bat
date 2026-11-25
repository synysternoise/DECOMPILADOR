@echo off
chcp 65001 >nul
title Atualizar Consulta de Placards
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo.
  echo Python nao encontrado neste computador.
  echo Instale pelo python.org marcando "Add python.exe to PATH" e rode de novo.
  echo.
  pause
  exit /b 1
)

%PY% -c "import openpyxl" 2>nul || %PY% -m pip install --user openpyxl
%PY% -m placards_cd.publicar --config config.json
echo.
pause
