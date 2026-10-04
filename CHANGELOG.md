# Changelog

> **Language:** English · [Italiano](docs/it/CHANGELOG.md)

All notable changes to Korvaxoide PDF Editor. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning is
[semantic](https://semver.org/lang/en/).

The version lives in a single place, `__version__` in `pdfeditor/__init__.py`:
the AppImage name, the Windows executable name, the macOS bundle version and
the *About* window all read it from there.

---

## Unreleased

## 0.1.0 — 2026-10-04

The first numbered release. Before this the number was `1.0.0` by default and
meant nothing, because the program had never been published.

### Interface

The interface speaks Italian and English. The language follows the system by
default and can be changed at any time from *Tools ▸ Language…* or from the
preferences; menus and toolbars change straight away, open dialogs keep the
language they were built with. The source keeps its Italian strings: they are
the keys the English catalogue is written against, so a missing translation
shows the Italian sentence instead of a blank.

### Added

- **Signatures**: freehand drawing with pen pressure and opacity, typed
  signatures in calligraphic fonts, insertion from an image, background removal
  (sampled colour, magic wand, threshold, eraser brush), a signature library
  with renaming and reuse, placement into an existing signature field.
- **Digital signatures** PKCS#7 with a P12/PEM or self-signed certificate, and
  verification.
- **Forms**: reading and writing AcroForm fields (text, checkbox, radio button,
  combo box, push button, signature), in-place filling, creation of new fields
  with properties, flattening and resetting.
- **Annotations**: highlight, underline, strike out, squiggly, freehand ink,
  shapes, note, stamp, attachment, link. Permanent redaction.
- **Pages**: insert, duplicate, delete, extract, merge, split, reorder, rotate,
  crop, numbering, page setup.
- **Search and replace** with case, whole word and regular expressions, on
  scanned PDFs too thanks to OCR.
- **Security**: open password, permissions, AES-256 encryption, protection
  removal, quality and accessibility checks.
- **Export** to PNG/JPEG/TIFF, text, PDF/A (with Ghostscript), and printing.
- **Preview of the signature** with the option to sign the open PDF.
- **Undo and redo** of every change.
- **Recovery**: a periodic copy, proposed at start-up after an unexpected
  shutdown.
- **Light and dark theme**, propagated to panels and dialogs.
- Run from the source on Linux and Windows (`./run.sh`, `run.bat`), and
  PyInstaller binaries for both systems (AppImage and `.exe`).
- **English interface**, selectable and remembered, following the system when
  no choice has been made.
- Automated tests: 769 tests, an integration suite and an end-to-end check,
  run on Linux and Windows with Python 3.12 and 3.14.

### Changed

- The program is now called Korvaxoide PDF Editor everywhere it names itself:
  the window title, the *About* window, the menu entry, the macOS bundle, the
  producer written into every exported PDF and the documentation. The colon of
  the old "Korvaxoide: PDF Editor" is gone. The repository address, the file
  names and the configuration folders stay as they are: they belong to the
  installation rather than to the name on the label, and renaming them would
  strand the settings of the people already using the program.

### Fixed

Defects found by going through the program feature by feature; the full list,
with the cause of each one, is in the commit messages.

- On a rotated page every shape and every drag landed in the opposite corner:
  the view handed the engine screen coordinates while the document recorded
  page coordinates.
- Dragging across pages left the element on the wrong page.
- A click in the gap between pages selected with invented coordinates.
- Opening another file left a ghost selection behind: `Ctrl+C` and *Elimina*
  failed.
- Ticking a checkbox reopened its own editor and repeated the change
  indefinitely, making the page vanish from the view.
- In a radio-button group the parent covered all the options, so clicking any
  of them switched them all off; several options could stay on at once.
- Duplicating several pages picked the wrong ones and duplicated one of them
  twice.
- Selected text could not be cleared with a click.
- `Ctrl+S` did not save, with or without changes.
- Export lost title, author, subject and keywords.
- Text replacement lost font, size and colour, wiped table borders and put the
  new text under everything else on the page.
- Snapping only worked horizontally.
- Figures without alternative text were never reported.
- Printing ignored the chosen page range and had no guard on the resolution or
  on a printer error.
- The text windows discarded the font, size, colour and alignment they had
  collected, in favour of the toolbar's style.
- The alpha channel was lost when moving or extracting an image, and a
  palette-mode signature turned black.
- After removing protection, every later save was refused.
- Saving on Windows wrote nothing. MuPDF keeps open the file it opened the
  document from, and Windows does not allow an open file to be replaced, so the
  substitution always answered «Access is denied» and the new content was
  never written. When the file cannot be replaced the content is now written
  into it, after a few attempts: the file on disk stays valid and the reads
  that follow are the ones of the document just rewritten. A file that stays
  blocked by another program is now reported, instead of being passed off as
  saved.

The distribution was broken as well, and a release is exactly where that shows.

- The Linux build never got as far as the AppImage. The folder it assembled was
  named with a relative path and `appimagetool` was called from inside `dist/`,
  so it looked for `dist/dist/…`, found nothing and the build stopped with an
  error that says nothing about the cause. The path is now absolute.
- The AppImage could not start even when the folder was put together by hand:
  no `AppRun` was in it, so the runtime mounted the image, found nothing to run
  and left with «Failed to run AppRun». `build_linux.sh` now writes the `AppRun`
  that starts the program.
- The application-menu entry and the AppImage carried no icon. The file was
  installed under the name of the program while the menu entry asks for
  `korvaxoide-pdf-editor`, so the lookup found nothing and the entry kept the
  generic symbol.

### Documentation

- README as a presentation, with installation for Ubuntu and Windows.
- Complete manual, organised by topic.
- CONTRIBUTING with the code layout, the rules and the release procedure.
- THIRD-PARTY with the licence of every dependency and the reason for the AGPL.
- SECURITY with the private channel for security defects and the threat model.

### Tests

- The suite ran only on Linux: it read from `/tmp`, looked for fonts under
  `/usr/share/fonts`, counted a missing Ghostscript as a missing feature and
  built an impossible path out of a directory that does not exist. Temporary
  files, fonts and unusable paths now come from the helpers in
  `tests/ambiente.py`, on every platform.
- The GitHub runners did not install what the suite needs to start: the Qt
  platform libraries, so Linux failed at import, and the fonts, so the
  signature tests drew on nothing.
- The licence check failed the build when gnu.org could not be reached. A
  download that fails says nothing about the repository: it is now retried
  and, if the text still does not arrive, it warns and lets the build
  through. Only a changed `LICENSE` stops a build now.
- Fifty interaction tests failed on Windows before any click: the PDF used as
  a model was written over, file name included, while a window still had it
  open, and Windows refuses to rewrite it. Each test now builds its own
  model.
- The test for the retry when a file is briefly busy was skipped on Windows,
  where the substitution is never attempted: it now tries it on purpose, and
  a second test covers the retry of the write that Windows ends up using.
- The timer that closes the dialogs of a test kept running after the test was
  over, and closed the dialogs of the next ones: a signature drawn by hand
  vanished on its own.
- One test measured a drag in PDF points while the pointer travels in screen
  pixels: where a pixel is worth several points the field was moved correctly
  and the test failed anyway. It now measures where the pointer really went.
- A file left open could stop the whole suite, and a stopped suite kept the
  machine busy until the platform gave up six hours later. A dialog nobody
  closes is now closed after a few seconds, and every check has a time limit:
  a blocked check fails in minutes and says which one it was.
- Cut and paste on an element that does not accept them raised an internal
  error instead of saying so: the message was built with a word that did not
  match its own placeholder. Every message with a value inside is now checked
  against its placeholders.
- «Third-party notices» opened the browser for real, and on a machine without
  one the call never returned: the check that presses every menu item recorded
  the address instead.