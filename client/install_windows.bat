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

REM Creer les raccourcis de lancement
echo Creation des fichiers de lancement...

REM Client complet (PTT original)
(
echo @echo off
echo cd /d "%%~dp0\.."
echo python client\PTT_Client_Full.py
echo pause
) > "Lancer_TomatoPlan.bat"

REM Client simplifie
(
echo @echo off
echo cd /d "%%~dp0"
echo python PTT_Client.py
echo pause
) > "Lancer_TomatoPlan_Simple.bat"

echo.
echo ============================================
echo   Installation terminee!
echo ============================================
echo.
echo VERSION COMPLETE (recommandee):
echo   Double-cliquez sur "Lancer_TomatoPlan.bat"
echo   Interface 100%% identique a PTT v0.6.0
echo.
echo Version simplifiee:
echo   Double-cliquez sur "Lancer_TomatoPlan_Simple.bat"
echo.
echo Serveur: https://54.37.231.92
echo.
pause
