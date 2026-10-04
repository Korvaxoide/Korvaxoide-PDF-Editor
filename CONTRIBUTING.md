# Developing Korvaxoide PDF Editor

> **Language:** English · [Italiano](docs/it/SVILUPPO.md)

How the code is organised, how it is verified and how it is released.

The code itself is written with Italian docstrings and comments, like this
project's history. Keep new code consistent with the file you are editing.

---

## Contents

1. [Environment](#environment)
2. [Code layout](#code-layout)
3. [Project rules](#project-rules)
4. [Tests](#tests)
5. [Adding a feature](#adding-a-feature)
6. [Troubleshooting](#troubleshooting)
7. [Releasing](#releasing)
8. [Licence](#licence)

---

## Environment

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m pdfeditor
```

Python 3.12 or later is required. The dependencies are in `requirements.txt`.

For the tests you also need:

```bash
./venv/bin/pip install pytest
```

Optional external programs: `tesseract` (OCR) and `ghostscript` (PDF/A).
Nothing fails without them: the corresponding menu entries are greyed out and
explain why.

---

## Code layout

```
pdfeditor/
  __init__.py          name, version, identifiers
  __main__.py          entry point for "python -m pdfeditor"
  app.py               start-up: environment, translator, QApplication
  core/                the PDF engine, no interface
    document.py        pages, annotations, fields, text, images, security
    geometry.py        rectangles, rotations, intersections, snapping
    history.py         undo and redo
    settings.py        preferences on disk (JSON)
    textlayout.py      measuring text and laying it out
    units.py           page sizes and units
  ui/                  the interface
    main_window.py     window, menus, toolbars, actions
    page_view.py       scrolling view and drawing tools
    page_items.py      page nodes, fields, selection
    panels.py          side panels
    thumbnails.py      page thumbnails
    toolbars.py        toolbars and the tool menu
    dialogs/           dialog windows
    printing.py        printing and export
    theme.py           colours, metrics, stylesheet
    icons.py           drawing the icons
    ocr.py             text recognition
  features/            document quality, digital signatures
  signature/           library, drawing and rendering of signatures
tests/
  test_document.py     the PDF engine
  test_ui.py           the interface
  test_interazione.py  real events on the window
  test_funzionalita.py every feature, one at a time
  test_dialoghi.py     every dialog opens and fits the screen
  conftest.py          shared fixtures
  integration.py       complete flows
  finale.py            end-to-end check
  visual.py            interface captures
tools/
  make_icons.py        generates the icons (they are not in the repository)
resources/
  korvaxoide-pdf-editor.desktop   application-menu entry
```

---

## Project rules

### The engine does not know about the interface

`core/` imports nothing from `ui/`. Everything the interface can ask of the
document is a public method of `Document`.

### Every change goes through `_mutate`

```python
def _mutate(self, testo, fn, result_index=-1, emit_pages=False):
    before = self.snapshot() if self._undo_enabled else b""
    try:
        out = fn()
    except Exception:
        if before:
            self._restore(before)      # a failed operation leaves no mess
        raise
    if before and self._undo_enabled:
        self.history.run(SnapshotCommand(self, testo, before, self.snapshot()))
    ...
```

Writing straight to the pages skips undo: that is how text replacement lost the
text with no way to undo it, and how "Change page size" could not be undone with
`Ctrl+Z` until it became the public method `Document.set_page_size`.

The closure passed to `_mutate` **must return a value** if the method reports an
outcome: `bool(self._mutate(...))` on a closure that returns nothing is always
`False`, and a caller that checks the result reads "did not work" even when
everything did.

### Scene coordinates are in points

The scale is applied by the view's transform (`set_zoom` calls `setTransform`).
The code converting between page space and scene space uses the three methods
of `PdfView`:

- `_scene_rect(page, rect)` — for the page to the scene;
- `_scene_point(page, point)`;
- `_page_local(page, scene_point)` — to come back.

None of them multiplies by the zoom. Doing so was a bug: at 200% every element
ended up in the wrong place, because the zoom was applied twice.

The inverse conversions go through `Document.to_display_rect` and
`Document.to_page_rect`, which account for the PDF's rotation and the view's.

### Attributes must not hide QWidget methods

`QWidget` has the methods `size()`, `width()`, `height()`, `font()`, `rect()`,
`palette()`. Assigning an attribute with the same name makes them unreachable
from Python: a `dialog.size()` on a dialog that has `self.size = QSpinBox()`
raises an error. Dialog widgets have their own names (`size_box`, `width_box`,
`font_box`).

### Dialogs fit the screen

Every dialog calls `dlgutil.adatta_a_schermo(self, width, height)` at the start
of its constructor. The function:

1. reduces the size to what is available;
2. if the minimum content does not fit, puts it in a scrollable area.

Without this, on a small screen the buttons end up off-screen and the feature
looks broken.

### The theme propagates by itself

`theme.attiva(pal)` sets the palette in use and `theme.corrente()` returns it.
Windows and panels read it when they are built (`self.palette =
theme.corrente()`), so they do not have to be told one by one when the theme
changes. Whoever draws by hand receives `set_palette_colors` instead, called by
`MainWindow._apply_theme` for all the panels.

### Fonts are chosen by coverage, not by name

`typed.list_fonts()` sorts fonts by the glyphs they really contain
(`ha_lettere`), not by what the file name says: many fonts with "script" in the
name cover an ancient script, and the text comes out as a row of rectangles.

### Menu actions must be kept alive

In PySide6 a `QAction` with no Python references is collected and disappears
from the menu. `MainWindow._azioni_menu` holds them all. And they must be
created **without** passing `None` as the icon:

```python
# wrong: with a None icon PySide6 picks the wrong overload and
# the action comes out with no text
a = QAction(None, testo, self)

# right
a = QAction(testo, self)
if icona:
    a.setIcon(icons.icon(icona, ...))
```

Shortcuts belong **only** in the menus. If a toolbar defines them too, Qt flags
them as ambiguous and ignores them.

### The shortcut help is derived from the menus

`MainWindow._elenco_scorciatoie()` reads the shortcuts from the menu entries and
builds the list. The list used to be written by hand and promised things the
program did not accept: "Ctrl+G" for the grid (which was `Ctrl+'`), single
letter keys for the tools (never registered) and `Ctrl+W` to close (an action
that never existed). A hand-written list always drifts away from what the
program does; this one cannot.

### Single-letter keys do not register

Form fields are filled inside the main window, so they share the shortcut
context: a `V` shortcut on the window would scatter typing into the fields.
This is why V/H/T/S/I are a reminder in the tooltips and not shortcuts, and why
the help does not list them.

### A hand-drawn icon must not fail silently

`icons._disegna()` warns with a `RuntimeWarning` if the drawing raises.
Previously the error was swallowed: `Qt.RashCap` instead of `Qt.RoundCap` made
the default tool's icon disappear entirely, and the toolbar had an empty square
with no diagnosis. `test_ui.py` draws every icon and checks that none come out
empty and that they take the theme's colour.

### PyMuPDF inflates the annotation box

`annot.rect` returns the `/Rect` with the border included, and `set_rect`
writes the `/Rect` widened by `max(stroke, 2) / 2` on each side. Rewriting the
value that was just read inflated the annotation by two points on every move: a
100×60 rectangle, dragged four times, ended up 110×70. `Document._rect_come_lettorlo`
strips the box before writing it, and `test_document.py` checks that the
measurements stay constant.

### A name derived from a string is not a name

The "Checkbox" tool is called `field_check` and the code derived its type with
`tool.replace("field_", "")`, arriving at `check`: a name that does not exist in
`WIDGET_TYPES`. Every checkbox died with "Unsupported field type: check". The
correspondence is now the table `main_window.FIELD_TOOLS`, and the general rule
holds: **if a name is derived from a string, look it up in a table, not with a
substitution**.

The same goes for the window's combo pairs: in the font dialogs the pair was
reversed (it displayed the internal code and kept the extended name), `findData`
found nothing, the combo stayed empty and the values reported the string
`"None"`. The font chosen for a field always ended up as Helvetica.

### An option that is offered must change something

Three examples, all found by exercising the interface:

- "Whole word" compared `needle in testo`, that is a substring: it was always
  true and "ore" matched inside "Lorem";
- replacement received neither `case` nor `whole_word` from the search window:
  the two boxes had no effect when replacing;
- "JPEG quality" reached `extract_page_image` without the parameter, and the
  `B`/`I`/`U` levers only wrote a message.

When a window collects an option, it must be passed to the engine, and the
engine must use it. Better still: if a public parameter is useless, remove it, so
that it promises nothing (`_mutate(result_index=…)`, `hide_field_editor(commit=…)`).

### Windows that open must be exercised with real values

A check that builds every dialog and closes it with `reject` only verifies that
the window opens. With `accept` and plausible values everything after that is
exercised too, and that is where the defects are. It applies to ranges too:
`parse_range` must answer to `1-`, `-2`, `abc` and `1-99`, and an unreadable
range must be a stated error, not an empty list that the caller silently
replaces with the current page.

### What is on top wins under the cursor

The link test used to come before every other one in a click, and it always
won: an annotation resting on a link could not be selected, moved, resized or
deleted, and with the drawing tools a click opened the browser instead of
drawing. The correct order is: handles, fields, annotations and images, **then**
the link — and the link is only tested with the select tool.

### A dependency that is never imported is dead weight

`reportlab` and `pikepdf` were in `requirements.txt`, in `THIRD-PARTY.md`, in
the licences window and checked by the CI, but the program never imported them.
The CI now has a step that checks the opposite: every declared dependency must
appear among the imports in `pdfeditor/`. Optional dependencies (scipy, for
background removal) are declared as optional, not as required.

### Moving an image is not deleting and reinserting it

`Document.move_image` re-reads the image and reinserts it, because images are
not annotations and cannot be moved on their own. But MuPDF, when it deletes an
image, leaves a one-pixel placeholder in its place: on the second move the new
image landed on that placeholder and **vanished from the file**. With a
signature inserted by the program that meant dragging it twice made it
disappear.

Reopening the document from its own bytes between the deletion and the
reinsertion rebuilds the resource dictionary and solves it. It costs one
serialisation, which the project already pays on every change.

Two consequences to keep in mind: `image_rects` must discard the placeholders
(a one-pixel image is not an image of the document, but it was ending up in the
inventory and under the cursor), and the image's `xref` changes on every move,
so whoever holds a selection must recompute it.

### Documentation cannot promise more than the program does

The manual promised a search with "special characters" (regular expressions:
`search_for` takes the text literally), three positions on the page for
numbering (they are three positions at the foot), a mistyped shortcut
(`Maiusc+Invò`) and an HTML export that does not exist. If a fix changes the
behaviour, the documentation line is corrected along with it.

### Every icon and menu entry is rebuilt when the theme changes

The icons are drawn by hand and take their colour from the palette, so
`MainWindow._apply_theme` calls `toolbars.refresh_icons`. The resize-handle
colours live in `Palette` and not in `Metrics`: with the colours hardcoded to
the light theme they stayed white in the dark theme too.

---

## Tests

```bash
./venv/bin/python -m pytest tests/ -q         # everything
./venv/bin/python -m pytest tests/test_funzionalita.py -q
./venv/bin/python -m pytest tests/test_dialoghi.py -q
./venv/bin/python -m pytest tests/test_interazione.py -q
./venv/bin/python -m pytest tests/test_documentazione.py -q
./venv/bin/python tests/integration.py
./venv/bin/python tests/finale.py
./venv/bin/python tests/visual.py
```

On a single platform, layout problems escape. The interaction suite must also
be run on a real graphical session:

```bash
unset QT_QPA_PLATFORM
XDG_SESSION_TYPE=wayland ./venv/bin/python -m pytest tests/test_interazione.py -q
```

### The tests do not write to the user's data

`tests/ambiente.py` moves configuration and data to a temporary directory
before any import of the program, and has to be called **before anything
else**, including from the standalone scripts:

```python
import ambiente

ambiente.configura_qt()
ambiente.isola()
ambiente.prepara_percorso()
```

Without this the suite wrote into the real preferences and built a signature
library on the user's machine: a test that changed the theme or disabled
recovery left the program with different settings, and you found out only at the
next run, after restarting the application.

The directories are computed on every call by reading environment variables, so
moving them is enough: no hook point in the code is needed.

### The tests have to run on Windows too

The suite runs on Linux and on Windows, and a test that passes on one system
and fails on the other is a defect in the test, not in the machine. Two
families of assumptions caused most of them:

- **Paths that only exist on one system.** `/tmp/...`, `/usr/share/fonts/...`
  and `/bin/true` do not exist on Windows, and a permission error raised by the
  operating system is not a property of the program either. Temporary files go
  through `ambiente.cartella(...)` and `ambiente.ricrea(...)`, which give a
  directory under the one the suite already isolated, and the tests that need
  an unusable path build it from a file and a directory that cannot coexist.
- **Fonts that only exist on one system.** A signature drawn with a font that
  is not installed does not fail, it comes out empty or covered in squares,
  and the test that only checks that the file was written says nothing about
  it. `ambiente.font_serif()` returns a font that is really there, and a test
  that needs one skips itself when there is none, saying why.

The same rule applies to the standalone scripts: they are run in CI too, so
they take their fonts and their folders from `ambiente`.

### What the tests cover

| File | What it verifies |
| --- | --- |
| `test_document.py` | the PDF engine, line by line |
| `test_security.py` | digital signatures, encryption and permissions |
| `test_signature.py` | strokes, rendering and background removal |
| `test_quality.py` | quality and accessibility checks |
| `test_core.py` | geometry, history, units, text layout |
| `test_ui.py` | windows, panels, themes, icons |
| `test_interazione.py` | real clicks, keystrokes and shortcuts |
| `test_funzionalita.py` | every feature, one at a time |
| `test_dialoghi.py` | every dialog opens and fits the screen |
| `test_regressioni.py` | defects found going through the engine feature by feature |
| `test_regressioni_ui.py` | the same defects, with real mouse events |
| `test_documentazione.py` | links, anchors and files the documents cite |
| `integration.py` | complete flows from beginning to end |
| `finale.py` | end-to-end check of the application |
| `visual.py` | captures for comparison by eye |

### Why exercise the interface and not only the methods

The worst defects so far are invisible when you only call the methods:

- menus emptied themselves because the actions were collected;
- the blue box around a field did not line up with the input, because the zoom
  was applied twice, once in the view and once in the conversions;
- the signature pad accepted no stroke at all, for two different `TypeError`s;
- presentation mode could be entered but not left;
- the signature ended up in an arbitrary place and could not be moved, because
  images were not looked for among the grabbable elements;
- the typed signature came out as a row of squares, from an ancient-script font
  chosen by file name.

A test that calls `w.action_signature()` and checks the return value would pass
all the same. Events are what is needed.

---

## Adding a feature

1. **The engine**: a public method on `Document` that uses `self._mutate(...)`.
2. **The action**: an `action_…` method on `MainWindow` that calls the engine,
   uses `self._busy_start()` if it is slow, `self._error(exc, "…")` on failure
   and `self._status("…")` to say what happened.
3. **The menu entry**: `self._mi(menu, "Text", "Ctrl+K", self.action_…, "icon")`.
   One shortcut, never two.
4. **The test**: one in `test_funzionalita.py` that performs it, and if windows
   are involved also in `test_interazione.py`.
5. **The documentation**: a line in the README and in the manual.

A feature is not finished until it has the test that exercises it.

### Documentation languages

The documents at the root of the repository are English and are the reference
ones; the Italian versions live in `docs/it/` and are updated alongside them.
Both are covered by `tests/test_documentazione.py`, which checks links, anchors
and cited files in every language: changing a file name in one language and not
in the other makes the suite fail.

---

## Troubleshooting

### An action does nothing

Is the entry disabled? Check `isEnabled()`. Then check that the menu was
rebuilt: new actions have to be added to `_azioni_menu`.

### The coordinates do not add up

Check that the conversion goes through `_scene_rect`/`_page_local` and that
`PageNode` has no size derived from the zoom: the node measures the page in
points, the view applies the scale.

### The drawing is wrong

Compare the drawn boundary with the expected one by sampling the image's pixels.
With a colour reference (the page's white border, a coloured block) the
comparison holds on every platform; with a grey border it gets confused with
antialiasing.

### A dialog opens but is not visible

Call `dlgutil.adatta_a_schermo` and check `minimumSizeHint()` against the
screen height.

### The text comes out in a strange order

`Page.insert_text` appends the text at the end of the content stream: the
position is right, the reading order is not. `Document.text()` reorders by
position, joining the blocks of the same line.

---

## Releasing

1. All tests green, including on a real Wayland session.
2. Update the version in `pdfeditor/__init__.py`: it is the only place it
   lives, and the AppImage name, the Windows executable name, the macOS bundle
   version and the About window all read it from there. The format is
   `MAJOR.MINOR.PATCH` and a test checks it.
3. Update the test count in the README.
4. Icons: `./venv/bin/python -m tools.make_icons`
5. Linux: `./build_linux.sh --onedir` (AppImage with `appimagetool`)
6. Windows: `.\build_windows.ps1 -OneDir`
7. Update the licences list in `THIRD-PARTY.md`.
8. Update `CHANGELOG.md` with what changed in this version.
9. Commit with a message that explains the cause, not only the symptom.
10. Tag the release: `git tag -a v0.1.0 -m "Korvaxoide PDF Editor 0.1.0"`, then
    push the tag. The tag is what makes the AGPL source obligation easy to
    meet: the release page offers the matching source in one click.

Version `0.1.0` is the first numbered one: before it the version was `1.0.0` by
default and meant nothing, because the program had never been published.

---

## Licence

AGPL-3.0-or-later. See [`LICENSE`](LICENSE) and
[`THIRD-PARTY.md`](THIRD-PARTY.md).

The licence is imposed by PyMuPDF (AGPL). Anyone who wants Artifex's commercial
licence can buy it and replace the library.