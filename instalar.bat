@echo off
chcp 65001 > nul
echo.
echo  ==========================================
echo   VIGIA - IAJA Compliance Monitor
echo   Instalacao do Ambiente
echo  ==========================================
echo.

:: Verifica se Python está instalado
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo  ERRO: Python nao encontrado.
    echo  Baixe e instale em: https://www.python.org/downloads/
    echo  Marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo  Python encontrado. Criando ambiente virtual...
python -m venv venv

echo  Ativando ambiente...
call venv\Scripts\activate

echo  Instalando bibliotecas (aguarde, pode demorar alguns minutos)...
pip install -r requirements.txt

echo.
echo  ==========================================
echo   Instalacao concluida com sucesso!
echo   Use o executar.bat para abrir o VIGIA.
echo  ==========================================
echo.
pause
