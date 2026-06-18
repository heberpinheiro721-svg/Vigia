@echo off
setlocal

set VENV=%USERPROFILE%\vigia_venv
set PROJ=%~dp0

echo Verificando ambiente...

if not exist "%VENV%\Scripts\streamlit.exe" (
    echo ERRO: streamlit nao encontrado em %VENV%
    pause & exit /b 1
)

cd /d "%PROJ%"
echo Iniciando VIGIA... Aguarde.
echo.

"%VENV%\Scripts\streamlit.exe" run app.py --server.headless false 2> st_err.txt

echo.
echo VIGIA encerrou. Verificando erros...
echo.
type st_err.txt
echo.
pause
