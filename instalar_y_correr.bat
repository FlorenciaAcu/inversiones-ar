@echo off
echo ====================================
echo  Inversiones AR - Backend
echo ====================================
echo.
echo Instalando dependencias...
pip install -r requirements.txt
echo.
echo Iniciando servidor en http://localhost:8000
echo Presiona Ctrl+C para detener.
echo.
python main.py
pause
