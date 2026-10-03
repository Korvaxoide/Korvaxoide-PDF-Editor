@echo off
REM Avvia Korvaxoide: PDF Editor da sorgente (Windows).
REM
REM   run.bat            installa se serve e avvia il programma
REM   run.bat --solo     installa le dipendenze senza avviare
REM
REM NumPy 2.5 richiede Python 3.12 o successivo. Senza il controllo qui sotto
REM pip risponde solo "requires a different Python", senza dire quale versione
REM manca, e il messaggio precedente indicava 3.11, che non basta.
setlocal
cd /d "%~dp0"

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>nul
if errorlevel 1 goto python_troppo_vecchio

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

:python_troppo_vecchio
echo Python 3.12 o superiore: e' il requisito di NumPy, e senza non si
echo possono installare le dipendenze.
python -c "import sys; print('Trovato Python %d.%d' %% sys.version_info[:2])" 2>nul
echo.
echo Se hai Python 3.12 o successivo gia' installato, puoi indicarlo qui:
echo     py -3.12 -m venv venv
echo     venv\Scripts\pip.exe install -r requirements.txt
echo     venv\Scripts\python.exe -m pdfeditor
pause
exit /b 1
