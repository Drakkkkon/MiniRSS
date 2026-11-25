@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================
echo          Сборка MiniRSS.exe
echo ======================================
where py >nul 2>nul
if errorlevel 1 (
  echo Не найден Python. Установите Python 3.10 или новее с сайта python.org.
  echo При установке отметьте пункт Add Python to PATH.
  pause
  exit /b 1
)
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить зависимости.
  pause
  exit /b 1
)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
py -m PyInstaller --noconfirm --clean --onefile --windowed --name MiniRSS --icon=assets\minirss.ico --add-data "assets;assets" --collect-all pystray --collect-all winotify --collect-all PIL --hidden-import winotify mini_rss.py
if errorlevel 1 (
  echo Сборка завершилась с ошибкой.
  pause
  exit /b 1
)
echo.
echo Готово! Файл находится здесь:
echo %~dp0dist\MiniRSS.exe
echo.
echo Для локальной подготовки GitHub Release запустите make_update_package.bat.
pause
