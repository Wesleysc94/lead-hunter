@echo off
title Lead Hunter Dashboard
cd /d "%~dp0"

echo.
echo  ==========================================
echo    LEAD HUNTER  ^|  Dashboard
echo  ==========================================
echo.

:: Verifica se Flask está instalado
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [Instalando Flask...]
    pip install flask --quiet
    if %errorlevel% neq 0 (
        echo  [ERRO] Nao foi possivel instalar o Flask.
        echo         Verifique se o Python esta instalado corretamente.
        pause
        exit /b 1
    )
    echo  [Flask instalado com sucesso!]
    echo.
)

:: Verifica se a porta 5000 já está em uso
netstat -ano | findstr ":5000 " >nul 2>&1
if %errorlevel% equ 0 (
    echo  [INFO] Porta 5000 ja em uso. Abrindo navegador...
    timeout /t 1 /nobreak >nul
    start "" "http://127.0.0.1:5000"
    goto :fim
)

echo  [Iniciando servidor na porta 5000...]
start "" /B python dashboard\app.py

echo  [Aguardando servidor iniciar...]
timeout /t 2 /nobreak >nul

echo  [Abrindo navegador...]
start "" "http://127.0.0.1:5000"

echo.
echo  Dashboard rodando em: http://127.0.0.1:5000
echo  Feche esta janela para encerrar o servidor.
echo.

:fim
pause
