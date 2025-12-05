@echo off
REM ============================================================
REM TomatoPlan Client - Installation Windows
REM ============================================================

echo.
echo ============================================
echo   TomatoPlan Client - Installation
echo ============================================
echo.

REM Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe!
    echo.
    echo Telechargez Python depuis: https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" lors de l'installation.
    echo.
    pause
    exit /b 1
)

echo [OK] Python trouve
python --version
echo.

REM Installer les dependances
echo Installation des dependances...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] Installation des dependances echouee
    pause
    exit /b 1
)
echo [OK] Dependances installees
echo.

REM Creer le raccourci de lancement
echo Creation du fichier de lancement...
(
echo @echo off
echo cd /d "%%~dp0"
echo python PTT_Client.py
echo pause
) > "Lancer_TomatoPlan.bat"

echo.
echo ============================================
echo   Installation terminee!
echo ============================================
echo.
echo Pour lancer l'application:
echo   - Double-cliquez sur "Lancer_TomatoPlan.bat"
echo   - Ou executez: python PTT_Client.py
echo.
echo Serveur configure: https://54.37.231.92
echo.
pause
