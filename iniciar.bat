@echo off
rem Liga o sistema Medipreco. Duas vezes no arquivo, ou "iniciar.bat" no terminal.
cd /d "%~dp0"

rem Recusa iniciar se outra copia ja estiver ligada: duas copias na mesma porta fazem o navegador
rem mostrar a versao antiga sem avisar.
netstat -ano | findstr /R /C:":5000 .*LISTENING" >nul
if %errorlevel%==0 (
  echo.
  echo A porta 5000 ja esta em uso por outra copia do sistema.
  echo Feche as outras janelas do sistema e abra este arquivo de novo.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Primeira vez: instalando o ambiente, aguarde...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
echo.
echo Sistema ligado. Abra no navegador: http://127.0.0.1:5000
echo Para desligar, feche esta janela ou aperte Ctrl+C.
echo.
".venv\Scripts\python.exe" src\app.py
