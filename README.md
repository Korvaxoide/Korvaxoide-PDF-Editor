# Korvaxoide PDF Editor

> **Language:** English · [Italiano](docs/it/README.md)

A PDF editor for Linux and Windows, with signatures, forms and annotations.
No document ever leaves your computer: the program does not use the network.

![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)
![Qt](https://img.shields.io/badge/Qt-6-41cd52)
![License](https://img.shields.io/badge/license-AGPL--3.0-8b5cf6)
![Tests](https://img.shields.io/badge/tests-815%20passed-4c1.svg)

---

> **The interface is in Italian.** There is no English build yet, so this
> document names the menu entries exactly as they appear on screen
> (*File ▸ Salva*) and gives the English meaning next to them (*Save*).

## Contents

1. [What it does](#what-it-does)
2. [Installation](#installation)
3. [First run](#first-run)
4. [Features](#features)
5. [Keyboard shortcuts](#keyboard-shortcuts)
6. [Where the data lives](#where-the-data-lives)
7. [Optional external programs](#optional-external-programs)
8. [How the code is laid out](#how-the-code-is-laid-out)
9. [Tests](#tests)
10. [Further documentation](#further-documentation)
11. [License](#license)

---

## What it does

Korvaxoide PDF Editor is a complete PDF editor: annotate, fill forms, sign,
search and replace, recognise the text in scans, protect a document and
export it to other formats. It runs on Linux and Windows with the same
interface.

What sets it apart:

- **it fills AcroForm forms and saves them into the PDF**, it does not merely
  print them;
- **it signs by hand, by keyboard, from an image or from a library**, with
  size, opacity and flattening; once placed, a signature is an object like any
  other: you drag it and resize it;
- **it applies digital signatures** with a certificate (PKCS#12) and verifies
  the signatures a document already carries;
- **it flattens annotations and fields**, making a document no longer editable;
- **it really redacts**: the covered text is removed from the content stream,
  not merely painted over with a black rectangle;
- **it recognises text** (OCR) with Tesseract, when installed;
- **light and dark theme** for the window, panels, dialogs and field editors;
- **it checks the document before you share it**: fonts that are not embedded,
  enormous images, metadata that says too much;
- **it reduces file size** by recompressing the images that cost the most.

---

## Installation

Three ways to run it, in the order most people want them. Nothing else in this
README is needed if the first one works for you.

### Downloading a ready-made binary

Go to the [releases page](https://github.com/Korvaxoide/Korvaxoide-PDF-Editor/releases/latest)
and download the file for your system. There is nothing to install: the download
is one file that carries Python and the libraries inside it.

**Windows.** The file is named `KorvaxoidePDF-<version>.exe`, where `<version>`
is the number in the release title. Double-click it and the program starts. No
installer, no folder, nothing else to keep next to it.

> **The executable is not signed.** On Windows 11 with Smart App Control
> enabled, Windows warns that the app is unrecognised and offers *More info*.
> That is expected: the project has no code signing certificate, so the warning
> is about the missing signature and not about the program. Choose *Run anyway*.
> The warning is the same one Windows shows for any unsigned program.

**Linux.** The file is named `KorvaxoidePDF-<version>-x86_64.AppImage`:

```bash
chmod +x KorvaxoidePDF-<version>-x86_64.AppImage
./KorvaxoidePDF-<version>-x86_64.AppImage
```

`chmod +x` is needed because the executable bit is not preserved by the
download. No installation, no `sudo`, no Python.

Both files are named after the version they carry, so the names on the releases
page are always the ones to look for. Every release also links *Source code*,
which is the matching source of that exact binary.

### Running from source

**Python 3.12 or later** is required: it is NumPy's requirement, and without it
the dependencies cannot be installed.

Dependencies (`requirements.txt`):

| Package | Why |
| --- | --- |
| PySide6 ≥ 6.11 | Interface (Qt 6) |
| PyMuPDF ≥ 1.28 | PDF engine |
| Pillow, NumPy | Images |
| cryptography, asn1crypto | Digital signatures |

Optional: **scipy** (BSD-3-Clause); when installed it improves background
removal for signatures. The program works without it.

**Linux (Ubuntu).** No `sudo`, no change to the system: everything goes into
`venv/` inside the project directory.

```bash
sudo apt install python3-venv      # only if "python3 -m venv" does not work
git clone https://github.com/Korvaxoide/Korvaxoide-PDF-Editor.git
cd Korvaxoide-PDF-Editor
./run.sh
```

`run.sh` creates `venv/` if it is missing, installs the dependencies from
`requirements.txt` and starts the program. With `./run.sh --solo` it stops
after preparing the environment.

To start it later, and from anywhere, use `python3 -m pdfeditor` inside the
directory that holds `venv/`.

**On Ubuntu 22.04** the system `python3` is 3.10 and the environment cannot be
built: install `python3.12` and `python3.12-venv`, then use
`python3.12 -m venv venv`. On Ubuntu 24.04 and later nothing is needed.

**To uninstall:** delete `venv/` and the project directory.

There is no installation script. Running from the source is the supported way,
and that means no application-menu entry and no icons in
`~/.local/share/icons/`. If you want them, the pieces are still in the
repository: `venv/bin/python -m tools.make_icons` writes `resources/icons/`, and
`resources/korvaxoide-pdf-editor.desktop` is a ready-made menu entry pointing
at `run.sh`.

**Windows.** Python 3.12 or later, installed from the
[official installer](https://www.python.org/downloads/windows/) with the
**Add python.exe to PATH** option ticked. Extract the folder and:

```bat
run.bat
```

`run.bat` prepares `venv\`, installs the dependencies and starts the program;
with `run.bat --solo` it installs without starting. If the machine has several
Python versions and the one in `PATH` is too old, the script says so and
suggests `py -3.12`.

By hand, which is what `run.bat` does:

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m pdfeditor
```

On Windows there is no installation script: the program stays in the folder and
is started from there. To get it into the menu, create a shortcut to
`venv\Scripts\pythonw.exe` with `-m pdfeditor` as arguments and the project root
as working directory: `pythonw` does not open a console window. To open PDFs
with a double click, register
`HKCU\Software\Classes\Applications\pythonw.exe\shell\open\command`.

The program also looks for its external programs in `~/.local/bin`: put
`tesseract` there and it is found without configuring anything. See
[Optional external programs](#optional-external-programs).

### Building a binary yourself

**Linux** (single folder and AppImage):

```bash
./build_linux.sh --onedir      # dist/KorvaxoidePDF/KorvaxoidePDF
./build_linux.sh               # also an AppImage (needs appimagetool)
```

**Windows** (PowerShell):

```powershell
.\build_windows.ps1            # dist\KorvaxoidePDF.exe, a single file
.\build_windows.ps1 -OneDir    # dist\KorvaxoidePDF\ folder, portable
```

The icons are not in the repository, they are drawn: both scripts generate them
before invoking PyInstaller. On its own:

```bash
./venv/bin/python -m tools.make_icons
```

Linux produces a folder by default, because the AppImage is built by packing
that folder; Windows produces a single file, which needs no installer and
nothing beside it. Set `KorvaxoidePDF_ONEDIR=1` or `=0` to choose the layout by
hand on either system.

---

## First run

- **Open a document:** double-click a PDF, or use the folder button.
- **Open a recent file:** *File ▸ Apri recente* (Open recent).
- **Save:** `Ctrl+S`. *Salva come…* (Save as) chooses the path.
- **Nothing gets lost:** closing with unsaved changes asks what to do. On the
  next start, *Recupero* (Recovery) offers the last copy.

Settings live in *Strumenti ▸ Preferenze…* (Tools ▸ Preferences): grid,
snapping, field highlighting, light or dark theme, default compression.

---

## Features

### Pages

| Action | How |
| --- | --- |
| Insert a blank page | *Pagine ▸ Inserisci pagina vuota…* (Insert blank page) |
| Insert from another PDF | *Pagine ▸ Inserisci da file…* (Insert from file) |
| Duplicate | *Pagine ▸ Duplica* (Duplicate) |
| Extract to a new document | *Pagine ▸ Estrai in un nuovo documento…* |
| Split the document | *File ▸ Dividi documento…* (Split document) |
| Delete | *Pagine ▸ Elimina* (Delete) |
| Rotate | *Pagine ▸ Ruota a destra / a sinistra / di 180°*, or `Ctrl+Shift+←/→` |
| Rotate 180° | *Pagine ▸ Ruota di 180°* (Rotate 180°) |
| Size and orientation | *Pagine ▸ Impostazione pagina…* (Page setup) |
| Crop (scan borders) | *Pagine ▸ Ritaglia pagina…* (Crop page) |
| Number the pages | *Pagine ▸ Numerazione pagine…* (Page numbering) |
| Reorder | drag the thumbnails |

### Annotations

Highlight, underline, strike out, squiggly, note, stamp, shape (rectangle,
ellipse), line, arrow, freehand ink, polygon, text box, image, link,
redaction and signature.

Every annotation is selected with a click and moved by dragging it. The square
handles resize it; the status bar tells you at once whether something is
selected.

The appearance options (colour, width, fill, opacity) are under
*Annota ▸ Stile annotazione* and *Annota ▸ Stile evidenziazione*
(Annotation style, Highlight style).

*Annota ▸ Appiattisci annotazioni* (Flatten annotations) burns the annotations
into the content: afterwards they are no longer editable, and the program asks
before doing it.

### Forms

Existing fields are filled with a click and saved into the document. With field
highlighting on, every field is outlined.

- *Moduli ▸ Rileva campi e moduli* (Detect fields) finds fields that exist but
  are not declared as such;
- *Moduli ▸ Compila tutti i campi vuoti* walks through them in sequence;
- *Moduli ▸ Appiattisci campi* (Flatten fields) makes text fields non-editable;
- *Moduli ▸ Azzera campi* (Reset fields) returns them to their initial value.

**To move or resize a field**, use the *Seleziona* (Select) tool and
**Alt+click** on the field: a plain click opens the editor instead. The side
handles change its size.

*Moduli ▸ Campo di testo* (and the other field tools) create new fields: one
click on the page is enough, the default size is sensible and can be corrected
afterwards.

### Signatures

*Firma ▸ Inserisci firma…* (or `Ctrl+Shift+G`) opens a dialog with four tabs:
**Disegna** (Draw), **Tastiera** (Keyboard), **Immagine** (Image),
**Libreria** (Library).

The placement options sit under the tabs: page, size, opacity, flatten onto
white, and fill the signature field if the form has one.

- **Library:** *Firma ▸ Libreria delle firme…* (Signature library) to save,
  rename and reuse signatures.
- *Firma ▸ Compila campo firma* (Fill signature field) opens the signing
  window with the form's first signature field already selected.
- *Firma ▸ Firma digitale (certificato)…* signs with a PKCS#12 certificate.

The drawing pad accepts stylus pressure, when available.

### Digital signatures

*Firma ▸ Firma digitale (certificato)…* signs the document or an existing
signature field with a password-protected `.p12`/`.pfx` certificate. A signed
document can no longer be modified.

*Moduli ▸ Verifica firma digitale* and *Strumenti ▸ Verifica firme…*
(Verify signatures) check the signatures a document carries, reporting outcome,
issuer and date.

### Search and replace

`Ctrl+F` opens the search panel. Results are stepped through with the buttons or
with `F3` and `Shift+F3`, and the page is brought into view on its own (inside
the search field, `Enter` does it).

*Sostituisci…* (`Ctrl+H`) replaces a word or a phrase, with the option to
distinguish case and to limit the search to chosen pages. The same two options
apply to search and to replace: with *parola intera* (whole word), a replacement
does not touch the "elazione" inside "Relazione". Replacements can be undone
with `Ctrl+Z` too.

Replacing rewrites the page: the word is covered and the new one written in its
place, at the same size. The reading order stays what you see.

### Text recognition (OCR)

*Strumenti ▸ OCR (riconosce testo)…* applies Tesseract to the page images and
adds an invisible text layer. It needs `tesseract` installed with the Italian
language.

### Security

*Strumenti ▸ Proteggi documento…* (Protect document) sets the password to open,
the password to modify, and the permissions (print, copy, modify, annotate,
extract).

The program never loses encryption silently: saving a protected document
without the passwords is refused, and you are told so.

*Strumenti ▸ Verifica firme…* (Verify signatures) checks digital signatures.

### Export and quality

| Action | Where |
| --- | --- |
| Export (PNG/JPEG/TIFF images, text, PDF/A) | *File ▸ Esporta…* (Export) |
| Print | `Ctrl+P` |
| Reduce file size | *File ▸ Riduci dimensione del file…* |
| PDF/A | *File ▸ Esporta…* → PDF/A |
| Merge documents | *File ▸ Unisci documenti…* (Merge documents) |
| Turn photos into a PDF | *File ▸ Converti immagini in PDF…* |

*File ▸ Converti immagini in PDF…* (Convert images to PDF) turns a pile of
photos into a document: pick the images, put them in the order you want, choose
the page size, the margins and how many of them go on each page, and it writes
a new PDF and opens it. Opening a single image still does the obvious thing —
one page, shaped like the photo.

*File ▸ Riduci dimensione del file…* recompresses the images above a size
threshold and reports before and after, so you can see whether it is worth it.

The **Qualità** (Quality) panel lists the typical problems: fonts that are not
embedded, enormous images, metadata, hidden objects, annotations sitting on top
of the text. Each finding has a button that fixes it.

### Attachments and comments

*Annota ▸ Allega file…* (Attach file) attaches a file to the PDF. The
**Allegati** (Attachments) panel lists them and opens them.

The **Commenti** (Comments) panel lists text-carrying annotations: notes, text
boxes and stamps.

### Bookmarks

The **+** button in the **Segnalibri** (Bookmarks) panel creates a bookmark at
the current page. Rename with a double click, reorder with the arrows, delete
from the panel itself.

---

## Keyboard shortcuts

The full list is in *? ▸ Scorciatoie da tastiera* (`F1`).

### File

| Key | Action |
| --- | --- |
| `Ctrl+N` | Nuovo (New) |
| `Ctrl+O` | Apri… (Open) |
| `Ctrl+S` | Salva (Save) |
| `Ctrl+Shift+S` | Salva come… (Save as) |
| `Ctrl+E` | Esporta… (Export) |
| `Ctrl+P` | Stampa… (Print) |
| `Ctrl+Q` | Esci (Quit) |

### Edit

| Key | Action |
| --- | --- |
| `Ctrl+Z` | Annulla (Undo) |
| `Ctrl+Y` | Ripeti (Redo) |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` | Taglia, copia, incolla (Cut, copy, paste) |
| `Ctrl+A` | Seleziona tutto (Select all) |
| `Esc` | Deseleziona (Deselect) |
| `Delete` | Elimina (Delete the selection) |
| `Ctrl+F` | Trova… (Find) |
| `Ctrl+H` | Sostituisci… (Replace) |
| `Ctrl+D` | Proprietà del documento… (Document properties) |
| `Ctrl+,` | Preferenze… (Preferences) |

### View

| Key | Action |
| --- | --- |
| `Ctrl+0` | Adatta alla pagina (Fit page) |
| `Ctrl+1` | Adatta alla larghezza (Fit width) |
| `Ctrl+2` | Dimensione reale (Actual size) |
| `Ctrl++` / `Ctrl+-` | Ingrandisci, riduci (Zoom in, out) |
| `Ctrl+Shift+P` | Pannello pagine (Page panel) |
| `Ctrl+Shift+L` | Pannelli laterali (Side panels) |
| `Ctrl+Shift+F` | Presentazione (Presentation) |
| `Ctrl+'` | Griglia (Grid) |
| `F11` | Schermo intero (Full screen) |

### Pages and tools

| Key | Action |
| --- | --- |
| `Ctrl+Shift+←` / `→` | Rotate the page |
| `Ctrl+Shift+N` | Inserisci pagina vuota… (Insert blank page) |
| `Ctrl+Shift+A` | Seleziona tutte le pagine (Select all pages) |
| `Ctrl+Shift+G` | Inserisci firma… (Insert signature) |
| `Ctrl+Shift+D` | Firma digitale… (Digital signature) |
| `Space` + drag | Pan the page |
| `F3` / `Shift+F3` | Next, previous result |

---

## Where the data lives

The program does not use the network and writes to two directories of the
user's own:

| System | Configuration | Data |
| --- | --- | --- |
| Linux | `~/.config/korvaxoide-pdf-editor/` | `~/.local/share/korvaxoide-pdf-editor/` |
| Windows | `%APPDATA%\KorvaxoidePDF\` | `%APPDATA%\KorvaxoidePDF\` |
| macOS | `~/Library/Application Support/KorvaxoidePDF/` | same |

The data directory holds the saved signatures, the fonts found on the system
and the recovery copy.

Saved signatures and certificates are **never** embedded in the PDF without
being asked: a digital signature requires an explicit action.

---

## Optional external programs

Korvaxoide PDF Editor works without any of these; they add features.

| Program | Used for | Without it |
| --- | --- | --- |
| `tesseract` | Text recognition (OCR) | The entry is greyed out |
| `ghostscript` (`gs`) | PDF/A export | The entry is greyed out |

On Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-ita ghostscript
```

Tesseract can also be installed without root, in the user's own directory:
`run.sh` adds `~/.local/bin` to `PATH`, so dropping the executable there is
enough.

---

## How the code is laid out

```
pdfeditor/
  app.py              start-up, translator, environment settings
  core/               the PDF engine, without Qt
    document.py       pages, annotations, fields, text, security
    geometry.py       rectangles, rotations, snapping
    history.py        undo and redo
    settings.py       preferences on disk
    textlayout.py     measuring and laying out text
    units.py          page sizes (A4, Letter, …)
  ui/                 the interface
    main_window.py    window, menus, toolbars, actions
    page_view.py      scrolling view, drawing tools
    page_items.py     page nodes, fields, selection
    panels.py         side panels
    thumbnails.py     page thumbnails
    toolbars.py       toolbars and the tool menu
    icons.py          icons drawn at runtime, no image files
    theme.py          light and dark theme
    ocr.py            calling tesseract
    printing.py       printing, PDF/A conversion
    dialogs/          windows and small dialogs
  features/
    digitalsign.py    PKCS#7 digital signatures
    quality.py        quality and accessibility checks
  signature/          pad, strokes, background removal, library
tests/                automated tests
tools/                icon generation
```

The rules followed:

- **the engine does not know about the interface**: `core/` imports nothing
  from `ui/`;
- **every change goes through `_mutate`**: that is how undo works, and a failed
  operation leaves no half-applied change behind;
- **scene coordinates are in points**: the scale is applied by the view's
  transform, not by the code (mixing the two put elements in the wrong place);
- **every interface action is covered by a test** that performs it, rather than
  one that calls the method.

---

## Tests

```bash
./venv/bin/python -m pytest tests/ -q     # 815 tests
./venv/bin/python tests/integration.py    # 80 integration checks
./venv/bin/python tests/finale.py         # 46 end-to-end checks
./venv/bin/python tests/visual.py         # interface captures
```

The tests do more than call methods: `tests/test_interazione.py` drives the
window with real Qt events (clicks, drags, keystrokes) and
`tests/test_funzionalita.py` exercises every feature one at a time. That is what
found the worst defects: menus that emptied themselves, field boxes in the
wrong place, a signature pad that accepted no strokes.

`tests/test_regressioni.py` and `tests/test_regressioni_ui.py` collect the
defects found by going through the editor feature by feature, each with an
explanation of the failure: every shape and every drag on a rotated page, a
signature that turned black when dragged, printing that never started, a
comments panel that did not respond, radio buttons that switched themselves
off.

---

## Further documentation

| Document | Contents |
| --- | --- |
| English (this repository) | |
| [`MANUAL.md`](MANUAL.md) | Complete guide, by topic |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How the code works and how to release |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed from one version to the next |
| [`THIRD-PARTY.md`](THIRD-PARTY.md) | Dependency licences |
| [`SECURITY.md`](SECURITY.md) | How to report a security defect |

In Italian, under [`docs/it/`](docs/it/): [README](docs/it/README.md) ·
[Manuale](docs/it/MANUALE.md) · [Sviluppo](docs/it/SVILUPPO.md) ·
[Changelog](docs/it/CHANGELOG.md) · [Licenze](docs/it/THIRD-PARTY.md) ·
[Sicurezza](docs/it/SECURITY.md)

---

## License

AGPL-3.0-or-later. The full text is in [`LICENSE`](LICENSE).

The licence is imposed by **PyMuPDF**, which is AGPL: for anyone who prefers
Artifex's commercial licence, buying it and replacing the library is enough.

The AGPL is a copyleft, not a restriction: selling, distributing and modifying
the program are all permitted. The only obligation is that **whoever receives
the program also receives the source** of the same version.

That obligation is already met here: the code of every published version is
this repository, and every release on GitHub carries the matching tag. Whoever
downloads a binary finds the source of that exact file with one click on
*Source code* on the [releases page](https://github.com/Korvaxoide/Korvaxoide-PDF-Editor/releases),
or with:

```bash
git clone https://github.com/Korvaxoide/Korvaxoide-PDF-Editor.git
git checkout v0.1.1
```

Korvaxoide PDF Editor comes with no warranty: it is provided "as is".