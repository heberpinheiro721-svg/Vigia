@echo off
setlocal

set VENV=%USERPROFILE%\vigia_venv
set PROJ=%~dp0

echo.
echo  =============================================
echo   VIGIA -- Analise de Investimentos IAJA
echo  =============================================
echo.

:: Verifica se Python esta instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo Instale Python 3.12+ em https://python.org e tente novamente.
    pause & exit /b 1
)

:: Cria o venv se nao existir
if not exist "%VENV%\Scripts\python.exe" (
    echo Criando ambiente virtual em %VENV%...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo ERRO: nao foi possivel criar o ambiente virtual.
        pause & exit /b 1
    )
    echo Ambiente criado.
    echo.
)

:: Instala/atualiza dependencias
echo Verificando dependencias ^(aguarde na primeira vez^)...
"%VENV%\Scripts\pip.exe" install -q -r "%PROJ%requirements.txt"
if errorlevel 1 (
    echo AVISO: erro ao instalar dependencias. O app pode nao funcionar corretamente.
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
