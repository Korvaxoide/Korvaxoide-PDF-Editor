#!/usr/bin/env bash
# Costruisce la versione pacchettizzata per Linux.
#
#   ./build_linux.sh            -> AppImage in dist/
#   ./build_linux.sh --onedir   -> cartella portatile in dist/
#
# Richiede: python3-venv, pip, e (per l'AppImage) appimagetool.
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-appimage}"
DIST="dist"
NAME="KorvaxoidePDF"
# la versione viene letta dal pacchetto, senza bisogno di un interprete: il
# nome del file distribuito dice quale build e' quella installata
VERSIONE="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfeditor/__init__.py)"
VERSIONE="${VERSIONE:-0.0.0}"

echo "==> 1/5 ambiente di compilazione"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip >/dev/null
./venv/bin/pip install -r requirements.txt >/dev/null
./venv/bin/pip install "pyinstaller>=6.0" >/dev/null

echo "==> 2/5 icone"
./venv/bin/python tools/make_icons.py >/dev/null

echo "==> 3/5 icona del programma (Linux)"
ICON_DIR="$HOME/.local/share/icons/hicolor"
# il nome del file e' quello che chiede la voce di menu, cioe' il campo
# Icon= di resources/korvaxoide-pdf-editor.desktop: con un nome diverso la
# icona non viene trovata e la voce di menu resta con il simbolo generico
ICON_NAME="korvaxoide-pdf-editor"
mkdir -p "$ICON_DIR/256x256/apps" "$ICON_DIR/128x128/apps" "$ICON_DIR/64x64/apps"
cp resources/icons/korvaxoide_pdf_editor_256.png "$ICON_DIR/256x256/apps/$ICON_NAME.png"
cp resources/icons/korvaxoide_pdf_editor_128.png "$ICON_DIR/128x128/apps/$ICON_NAME.png"
cp resources/icons/korvaxoide_pdf_editor_64.png "$ICON_DIR/64x64/apps/$ICON_NAME.png"

if [ "$MODE" = "--onedir" ]; then
  echo "==> 4/5 PyInstaller (cartella portatile)"
  rm -rf build "$DIST/$NAME"
  ./venv/bin/pyinstaller KorvaxoidePDF.spec --noconfirm --distpath "$DIST" --workpath build
  echo "==> 5/5 fatto"
  echo
  echo "Eseguibile: $DIST/$NAME/$NAME"
  echo "Avvio:      $DIST/$NAME/$NAME"
  exit 0
fi

echo "==> 4/5 PyInstaller"
rm -rf build "$DIST"
mkdir -p "$DIST"
./venv/bin/pyinstaller KorvaxoidePDF.spec --noconfirm --distpath "$DIST" --workpath build

echo "==> 5/5 AppImage"
if ! command -v appimagetool >/dev/null 2>&1; then
  echo "appimagetool non trovato."
  echo "Scaricalo da https://github.com/AppImage/AppImageKit/releases"
  echo "La cartella compilata si trova in: $DIST/$NAME"
  exit 0
fi

# il percorso e' assoluto perche' poco sotto appimagetool viene lanciato
# dentro dist/, e da li' un percorso relativo punterebbe a dist/dist
APP_DIR="$PWD/$DIST/$NAME.AppDir"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin" "$APP_DIR/usr/share/applications" "$APP_DIR/usr/share/icons/hicolor/256x256/apps"
cp -r "$DIST/$NAME/." "$APP_DIR/usr/bin/"
cp resources/icons/korvaxoide_pdf_editor_256.png "$APP_DIR/usr/share/icons/hicolor/256x256/apps/$ICON_NAME.png"
cp resources/korvaxoide-pdf-editor.desktop "$APP_DIR/$NAME.desktop"
cp resources/korvaxoide-pdf-editor.desktop "$APP_DIR/usr/share/applications/$NAME.desktop"
cp resources/icons/korvaxoide_pdf_editor_256.png "$APP_DIR/$ICON_NAME.png"

# AppRun e' il punto di ingresso dell'immagine: senza questo file appimagetool
# la costruisce lo stesso, ma lanciandola il runtime non trova nulla da
# eseguire e l'AppImage esce subito con «Failed to run AppRun»
cat > "$APP_DIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/KorvaxoidePDF" "$@"
APPRUN
chmod +x "$APP_DIR/AppRun"

cd "$DIST"
appimagetool --no-appstream "$APP_DIR" "${NAME}-${VERSIONE}-x86_64.AppImage"
cd ..

echo
echo "Immagine creata: $DIST/${NAME}-${VERSIONE}-x86_64.AppImage"
echo "Per installarla:  chmod +x ${NAME}-${VERSIONE}-x86_64.AppImage"
