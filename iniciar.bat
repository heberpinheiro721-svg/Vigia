@echo off
setlocal

set VENV=%USERPROFILE%\vigia_venv
set PROJ=%~dp0

echo.
echo  =============================================
echo   VIGIA -- Analise de Investimentos IAJA
echo  =============================================
echo.

:: Se o venv ja existe, vai direto para instalacao de pacotes
if exist "%VENV%\Scripts\python.exe" goto instalar

:: Precisa criar o venv -- tenta encontrar Python
echo Criando ambiente virtual em %VENV%...

set PYTHON=
where py >nul 2>&1 && set PYTHON=py
if "%PYTHON%"=="" where python >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
    ) do (
        if "%PYTHON%"=="" if exist %%P set PYTHON=%%P
    )
)

if "%PYTHON%"=="" (
    echo ERRO: Python nao encontrado.
    echo Instale Python 3.11+ em https://python.org ^(marque "Add to PATH"^) e tente novamente.
    pause & exit /b 1
)

%PYTHON% -m venv "%VENV%"
if errorlevel 1 (
    echo ERRO: nao foi possivel criar o ambiente virtual.
    pause & exit /b 1
)
echo Ambiente virtual criado.
echo.

:instalar
echo Verificando dependencias ^(aguarde na primeira vez^)...
"%VENV%\Scripts\pip.exe" install -q -r "%PROJ%requirements.txt"
if errorlevel 1 (
    echo AVISO: erro ao instalar alguma dependencia.
    echo.
)

cd /d "%PROJ%"
echo.
echo Iniciando VIGIA em http://localhost:8501
echo Pressione Ctrl+C para encerrar.
echo.

"%VENV%\Scripts\streamlit.exe" run app.py

echo.
echo VIGIA encerrado.
pause
