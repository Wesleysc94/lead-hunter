@echo off
title Agendador Semanal - Lead Hunter
cd /d "%~dp0"

echo.
echo  ==========================================
echo    LEAD HUNTER  ^|  Agendamento Semanal
echo  ==========================================
echo.
echo  Este script cria uma tarefa no Windows Task Scheduler
echo  para rodar o pipeline todo domingo as 07:00.
echo.
echo  ATENCAO: Execute como Administrador para melhor resultado.
echo.

set TASK_NAME=LeadHunterSemanal
set PYTHON_PATH=python
set SCRIPT_PATH=%~dp0main.py
set WORK_DIR=%~dp0

:: Remove tarefa existente se houver
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

echo  [Criando tarefa agendada...]
echo.

:: Tenta com SYSTEM (requer admin)
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" --skip-email" ^
    /sc WEEKLY ^
    /d SUN ^
    /st 07:00 ^
    /ru SYSTEM ^
    /f >nul 2>&1

if %errorlevel% equ 0 (
    echo  [OK] Tarefa criada com usuario SYSTEM
    goto :sucesso
)

:: Fallback: tenta com usuario atual
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\" --skip-email" ^
    /sc WEEKLY ^
    /d SUN ^
    /st 07:00 ^
    /ru %USERNAME% ^
    /f >nul 2>&1

if %errorlevel% equ 0 (
    echo  [OK] Tarefa criada com usuario %USERNAME%
    goto :sucesso
)

echo  [ERRO] Nao foi possivel criar a tarefa.
echo         Tente executar este .bat como Administrador
echo         (clique com botao direito > Executar como administrador)
echo.
pause
exit /b 1

:sucesso
echo.
echo  ==========================================
echo    Tarefa criada com sucesso!
echo  ==========================================
echo.
echo  Nome da tarefa : %TASK_NAME%
echo  Frequencia     : Toda semana
echo  Dia e hora     : Domingo as 07:00
echo  Comando        : python main.py --skip-email
echo.
echo  Comandos uteis:
echo.
echo    Ver tarefa:
echo    schtasks /query /tn "%TASK_NAME%"
echo.
echo    Rodar agora:
echo    schtasks /run /tn "%TASK_NAME%"
echo.
echo    Remover agendamento:
echo    schtasks /delete /tn "%TASK_NAME%" /f
echo.

pause
