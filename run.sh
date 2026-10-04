#!/usr/bin/env bash
# Avvia Korvaxoide PDF Editor da sorgente (Linux/macOS).
set -euo pipefail
cd "$(dirname "$0")"

# I programmi opzionali installati per l'utente (per esempio Tesseract
# dall'AppImage) stanno in ~/.local/bin, che la sessione grafica non mette
# sempre nel PATH: senza questa riga l'OCR risulterebbe non disponibile
# quando il programma parte dal menu delle applicazioni.
if [ -d "$HOME/.local/bin" ]; then
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) PATH="$HOME/.local/bin:$PATH"; export PATH ;;
  esac
fi

if [ ! -d venv ]; then
  echo "Ambiente non trovato: creo la directory virtuale…"
  python3 -m venv venv 2>/dev/null || {
    echo "venv non disponibile. Installa python3-venv e riprova." >&2
    exit 1
  }
  ./venv/bin/pip install --upgrade pip
  ./venv/bin/pip install -r requirements.txt
fi

exec ./venv/bin/python -m pdfeditor "$@"
