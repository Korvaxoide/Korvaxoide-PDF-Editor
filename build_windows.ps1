# Costruisce l'eseguibile Windows (.exe) con PyInstaller.
#
# Da eseguire su Windows con Python 3.12, 3.13 o 3.14 (64 bit).
#   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
#   .\build_windows.ps1 -OneDir
param(
    [switch]$OneDir,
    [switch]$NoIcon
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# PySide6 6.11.2 dichiara "Requires-Python >=3.10,<3.15": su Python 3.15 pip
# non lo installa affatto. Senza il controllo qui sotto la compilazione
# proseguiva lo stesso (pip usciva con errore, ma PowerShell non lo trattava
# come fatale) e produceva un .exe da 10 MB che all'avvio non trovava PySide6.
$MINIMA = [version]"3.12"
$MASSIMA = [version]"3.15"

function Get-VersionePython {
    param(
        [string]$Eseguibile,
        [string[]]$Argomenti = @()
    )
    try {
        $out = & $Eseguibile @Argomenti -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or -not $out) {
        return $null
    }
    try {
        return [version](($out | Select-Object -Last 1).Trim())
    } catch {
        return $null
    }
}

Write-Host "==> 1/5 ambiente di compilazione" -ForegroundColor Cyan

# Si prova prima il python del PATH, poi il launcher py con le versioni
# supportate: chi ha installato Python 3.15 di solito ha ancora 3.13 o 3.14.
$candidati = @(
    @{ Eseguibile = "python"; Argomenti = @() },
    @{ Eseguibile = "py";     Argomenti = @("-3.14") },
    @{ Eseguibile = "py";     Argomenti = @("-3.13") },
    @{ Eseguibile = "py";     Argomenti = @("-3.12") }
)
$python = $null
$trovate = @()
foreach ($candidato in $candidati) {
    if (-not (Get-Command $candidato.Eseguibile -ErrorAction SilentlyContinue)) {
        continue
    }
    $versione = Get-VersionePython -Eseguibile $candidato.Eseguibile -Argomenti $candidato.Argomenti
    if ($null -eq $versione) {
        continue
    }
    $trovate += "$($candidato.Eseguibile) $($candidato.Argomenti -join ' ') -> Python $versione"
    if ($versione -ge $MINIMA -and $versione -lt $MASSIMA) {
        $python = @{
            Eseguibile = $candidato.Eseguibile
            Argomenti  = $candidato.Argomenti
            Versione   = $versione
        }
        break
    }
}

if ($null -eq $python) {
    if ($trovate.Count -gt 0) {
        Write-Host "    Versioni trovate: $($trovate -join '; ')" -ForegroundColor Yellow
    }
    throw ("Serve Python da 3.12 a 3.14, 64 bit. PySide6 6.11.2 non supporta " +
        "Python 3.15, quindi pip non riesce a installarlo e l'eseguibile non " +
        "partirebbe. Installa Python 3.14 da " +
        "https://www.python.org/downloads/windows/ (spunta «Add python.exe to " +
        "PATH») e rilancia questo script.")
}
Write-Host "    Uso Python $($python.Versione) ($($python.Eseguibile) $($python.Argomenti -join ' '))"

$venvPython = "venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $venvVersione = Get-VersionePython -Eseguibile $venvPython
    if ($null -eq $venvVersione -or $venvVersione -ne $python.Versione) {
        Write-Host "    La cartella venv esistente usa Python ${venvVersione}: la ricreo con $($python.Versione)" -ForegroundColor Yellow
        Remove-Item -Recurse -Force venv
    }
}
if (-not (Test-Path $venvPython)) {
    $argomentiPython = $python.Argomenti
    & $python.Eseguibile @argomentiPython -m venv venv
    if ($LASTEXITCODE -ne 0) {
        throw "Non sono riuscito a creare venv: controlla l'installazione di Python."
    }
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Aggiornamento di pip non riuscito."
}

& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw ("Installazione delle dipendenze non riuscita: le righe ERROR qui " +
        "sopra dicono quale pacchetto e perche'. La compilazione si ferma " +
        "qui, prima di produrre un eseguibile incompleto.")
}

# pip puo' uscire con 0 avendo lasciato un pacchetto a meta': la prova vera e'
# caricare tutto quello che l'eseguibile usera' all'avvio.
& $venvPython -c "import PySide6, PIL, fitz, numpy, cryptography, asn1crypto"
if ($LASTEXITCODE -ne 0) {
    throw "Le dipendenze installate non si caricano: non compilo un eseguibile che non partirebbe."
}

Write-Host "==> 2/5 icone" -ForegroundColor Cyan
& $venvPython tools\make_icons.py
if ($LASTEXITCODE -ne 0) {
    throw "Disegno delle icone non riuscito."
}

Write-Host "==> 3/5 PyInstaller" -ForegroundColor Cyan
& $venvPython -m pip install "pyinstaller>=6.0"
if ($LASTEXITCODE -ne 0) {
    throw "Installazione di PyInstaller non riuscita."
}

Write-Host "==> 4/5 controllo versione Python"
Write-Host "    Python $($python.Versione)"

Write-Host "==> 5/5 compilazione" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
$argomenti = @("KorvaxoidePDF.spec", "--noconfirm")
if ($OneDir) { $argomenti += "--onedir" }
& $venvPython -m PyInstaller @argomenti
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller non e' riuscito."
}

$eseguibile = if ($OneDir) { "dist\KorvaxoidePDF\KorvaxoidePDF.exe" } else { "dist\KorvaxoidePDF.exe" }
if (Test-Path $eseguibile) {
    $dim = [math]::Round((Get-Item $eseguibile).Length / 1MB, 1)
    # Il nome del file porta la versione: due build consecutive altrimenti
    # hanno lo stesso nome e non si distinguono.
    $versioneProgramma = & $venvPython -c "import sys; sys.path.insert(0, '.'); from pdfeditor import __version__; print(__version__)"
    $destinazione = Join-Path (Split-Path $eseguibile) "KorvaxoidePDF-$versioneProgramma.exe"
    Copy-Item $eseguibile $destinazione -Force
    Write-Host ""
    Write-Host "Compilazione completata: $eseguibile ($dim MB)" -ForegroundColor Green
    Write-Host "Copia con versione:        $destinazione" -ForegroundColor Green
    Write-Host "Le firme digitali e la cifratura funzionano senza componenti esterni."
} else {
    Write-Warning "Eseguibile non trovato in $eseguibile; guarda la cartella dist."
}
