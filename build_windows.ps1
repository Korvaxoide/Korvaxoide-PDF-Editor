# Costruisce l'eseguibile Windows (.exe) con PyInstaller.
#
# Da eseguire su Windows con Python 3.12 o superiore.
#   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
#   .\build_windows.ps1 -OneDir
param(
    [switch]$OneDir,
    [switch]$NoIcon
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "==> 1/4 ambiente di compilazione" -ForegroundColor Cyan
if (-not (Test-Path "venv")) {
    python -m venv venv
}
& .\venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\venv\Scripts\pip.exe install -r requirements.txt | Out-Null
& .\venv\Scripts\pip.exe install "pyinstaller>=6.0" | Out-Null

Write-Host "==> 2/4 icone" -ForegroundColor Cyan
& .\venv\Scripts\python.exe tools\make_icons.py | Out-Null

Write-Host "==> 3/4 controllo versione Python" -ForegroundColor Cyan
$versione = & .\venv\Scripts\python.exe -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Host "    Python $versione"
if ([version]$versione -lt [version]"3.12") {
    throw "Servono almeno Python 3.12: e il requisito di NumPy."
}

Write-Host "==> 4/4 PyInstaller" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
$argomenti = @("KorvaxoidePDF.spec", "--noconfirm")
if ($OneDir) { $argomenti += "--onedir" }
& .\venv\Scripts\pyinstaller.exe @argomenti
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller non e' riuscito."
}

$eseguibile = if ($OneDir) { "dist\KorvaxoidePDF\KorvaxoidePDF.exe" } else { "dist\KorvaxoidePDF.exe" }
if (Test-Path $eseguibile) {
    $dim = [math]::Round((Get-Item $eseguibile).Length / 1MB, 1)
    # Il nome del file porta la versione: due build consecutive altrimenti
    # hanno lo stesso nome e non si distinguono.
    $versioneProgramma = & .\venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); from pdfeditor import __version__; print(__version__)"
    $destinazione = Join-Path (Split-Path $eseguibile) "KorvaxoidePDF-$versioneProgramma.exe"
    Copy-Item $eseguibile $destinazione -Force
    Write-Host ""
    Write-Host "Compilazione completata: $eseguibile ($dim MB)" -ForegroundColor Green
    Write-Host "Copia con versione:        $destinazione" -ForegroundColor Green
    Write-Host "Le firme digitali e la cifratura funzionano senza componenti esterni."
} else {
    Write-Warning "Eseguibile non trovato in $eseguibile; guarda la cartella dist."
}
