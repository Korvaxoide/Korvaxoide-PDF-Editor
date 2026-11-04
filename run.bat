@echo off
REM Avvia Korvaxoide PDF Editor da sorgente (Windows).
REM
REM   run.bat            installa se serve e avvia il programma
REM   run.bat --solo     installa le dipendenze senza avviare
REM
REM PySide6 6.11.2 richiede Python >=3.10,<3.15: NumPy 2.5 chiede almeno 3.12,
REM e su Python 3.15 pip non installa PySide6. Il controllo guarda entrambi i
REM limiti, altrimenti pip risponde solo "requires a different Python".
setlocal
cd /d "%~dp0"

python -c "import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (3, 15) else 1)" 2>nul
if errorlevel 1 goto python_non_supportato

REM Un venv creato con una versione non supportata resta li' e non si aggiorna
REM da solo: va buttato, altrimenti run.bat continua a usarlo.
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe -c "import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (3, 15) else 1)" 2>nul
    if errorlevel 1 (
        echo L'ambiente venv esistente usa una versione di Python non supportata: lo ricreo.
        rmdir /s /q venv
    )
)

if not exist venv (
    echo Creo l'ambiente virtuale...
    python -m venv venv
    if errorlevel 1 (
        echo Il modulo venv non e' disponibile. Su Windows e' incluso
        echo nell'installatore ufficiale di Python: reinstalla Python e riprova.
        pause
        exit /b 1
    )
    call venv\Scripts\python.exe -m pip install --upgrade pip
    call venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo Installazione delle dipendenze non riuscita.
        pause
        exit /b 1
    )
)

if "%~1"=="--solo" (
    echo Dipendenze installate. Avvia con run.bat
    exit /b 0
)

venv\Scripts\python.exe -m pdfeditor %*
exit /b %errorlevel%

:python_non_supportato
echo Serve Python da 3.12 a 3.14: 3.12 e' il minimo di NumPy 2.5, 3.15 non e'
echo supportato da PySide6 6.11.2 e l'eseguibile non partirebbe.
python -c "import sys; print('Trovato Python %d.%d' %% sys.version_info[:2])" 2>nul
echo.
echo Se hai gia' Python 3.12, 3.13 o 3.14 installato, puoi indicarlo qui:
echo     py -3.14 -m venv venv
echo     venv\Scripts\pip.exe install -r requirements.txt
echo     venv\Scripts\python.exe -m pdfeditor
echo.
echo Altrimenti installa Python 3.14 da
echo https://www.python.org/downloads/windows/
pause
exit /b 1
