# Korvaxoide PDF Editor — Manual

> **Language:** English · [Italiano](docs/it/MANUALE.md)

Complete guide, organised by topic. For installation see the
[README](README.md).

> **The interface is in Italian.** Every menu entry below is named exactly as
> it appears on screen; the English meaning follows in brackets.

---

## Contents

1. [The interface](#the-interface)
2. [Documents](#documents)
3. [Pages](#pages)
4. [Viewing](#viewing)
5. [Selecting and copying](#selecting-and-copying)
6. [Annotations](#annotations)
7. [Forms](#forms)
8. [Signatures](#signatures)
9. [Digital signatures](#digital-signatures)
10. [Search and replace](#search-and-replace)
11. [Text recognition](#text-recognition)
12. [Protection](#protection)
13. [Exporting and converting](#exporting-and-converting)
14. [Document quality](#document-quality)
15. [Attachments and comments](#attachments-and-comments)
16. [Bookmarks](#bookmarks)
17. [External programs](#external-programs)
18. [Frequent problems](#frequent-problems)

---

## The interface

```
┌──────────────────────────────────────────────────────────────┐
│ toolbar: open, save, print, find, tools, zoom               │
├────────────┬────────────────────────────────┬────────────────┤
│  Pages     │        the document            │  side panel:   │
│  (scrollable│        (the view)             │  search,      │
│   thumbnails)                              │  fields,      │
│            │                                │  bookmarks,   │
│            │                                │  comments,    │
│            │                                │  attachments, │
│            │                                │  tools        │
├────────────┴────────────────────────────────┴────────────────┤
│ status bar: current page, zoom, messages                    │
└──────────────────────────────────────────────────────────────┘
```

**The side panel** has one entry per tab. It opens and closes with
*Visualizza ▸ Pannelli laterali* (`Ctrl+Shift+L`).

**The status bar** is the most useful part while you work: it always says what
has just happened, which element is selected and what can be done with it.

**The tool button** at the top left shows the active tool. `Esc` goes back to
*Seleziona* (Select).

---

## Documents

### Opening

- double-click the file, or *File ▸ Apri…* (`Ctrl+O`);
- *File ▸ Apri recente* (Open recent) to go back to recent files;
- by dragging the file onto the window.

A protected document asks for the open password. If you do not remember it, it
can still be opened read-only by choosing to open without the password.

### Saving

- `Ctrl+S` saves in place;
- *File ▸ Salva come…* (`Ctrl+Shift+S`) chooses another path;
- *File ▸ Salva una copia…* (Save a copy) saves a copy and carries on working
  on the original.

`Ctrl+S` can be pressed even when nothing has changed: the file is rewritten as
it is. It is useful to regain write permissions lost along the way, or to put
back a file corrected by hand with another program.

**Careful:** saving a protected document without the passwords is **refused**,
with a notice. The program never produces an unprotected PDF quietly.

### Recovery

If the program closes unexpectedly, on the next start it offers the recovery
copy saved in `~/.local/share/korvaxoide-pdf-editor/`.

### Properties

*Modifica ▸ Proprietà del documento…* (Document properties) shows title, author,
subject, keywords, PDF creator, the application that produced the file,
modification date and page count. *XMP* opens the advanced metadata.

---

## Pages

### Ordering

The thumbnails on the left are dragged. Alternatively:
*Pagine ▸ Duplica* (Duplicate), *Estrai in un nuovo documento…* (Extract to a
new document) and *Elimina* (Delete), which act on the selected pages; hold
`Shift` or `Ctrl` to select several at once. *Pagine ▸ Seleziona tutte le
pagine* (`Ctrl+Shift+A`) selects the whole document.

### Rotating

- *Pagine ▸ Ruota a destra / a sinistra / di 180°* rotates the content;
- also the rotation buttons in the top toolbar, and the "Ruota a sinistra" /
  "Ruota a destra" entries in the thumbnails' context menu.

`Ctrl+Shift+right/left` rotates the current page.

Rotation concerns the page content: drawing tools, signatures and fields follow
the page as it is displayed, so you can draw over it as on a normal page.

### Cropping

*Pagine ▸ Ritaglia pagina…* (Crop page) removes the white or black borders of
scans. "Rileva il contenuto automaticamente" proposes the margins; they can be
corrected by hand in the four fields.

Cropping changes the page size: the content is neither modified nor moved, only
the visible area changes.

### Numbering

*Pagine ▸ Numerazione pagine…* (Page numbering) puts the number in one of the
three positions at the foot of the page (left, centre, right), with whatever
format you want (`{n}` is the number). You can choose to skip the first page and
to show the total as well (`{n}/{tot}`).

Numbering is a text layer: it shows on screen and in print, and can be removed
with *Pagine ▸ Rimuovi numerazione* (Remove numbering).

---

## Viewing

### Zoom

| Mode | Key | What it does |
| --- | --- | --- |
| Adatta alla pagina (Fit page) | `Ctrl+0` | the whole page |
| Adatta alla larghezza (Fit width) | `Ctrl+1` | the width of the page |
| Dimensione reale (Actual size) | `Ctrl+2` | 100% |
| Ingrandisci (Zoom in) | `Ctrl++` | by 25% |
| Riduci (Zoom out) | `Ctrl+-` | by 25% |

The mouse wheel scrolls the page; `Ctrl` with the wheel changes the zoom.

The button at the bottom right shows the percentage.

### Page modes

- **Continua** (continuous): pages one below another, the most common;
- **Pagina singola** (single page): one page at a time, with navigation;
- **Affiancate** (facing): two pages per screen, like a book.

*Visualizza ▸ Presentazione* (`Ctrl+Shift+F`) hides the panels and the
toolbars and shows one page at a time full screen. Leave with the same command
or with `Esc`.

### Reading tools

*Visualizza ▸ Griglia* shows a grid (`Ctrl+'`); *Magnetismo* (snapping) makes
annotations snap to the edges and centres of others, to the page edges and to
the grid, with guide lines drawn while you drag; *Evidenzia campi* (highlight
fields) outlines form fields.

*Visualizza ▸ Tema scuro* (Dark theme) inverts the colours. The dark theme
applies to everything: window, toolbars, side panels, thumbnails, dialogs and
the editor opened on a field. The choice is remembered across starts.

---

## Selecting and copying

With the **Seleziona** (Select) tool:

- click and drag on an annotation to select and move it;
- a click on a field opens it for filling;
- **Alt+click** on a field selects it instead of opening it, so it can be moved
  or resized;
- a drag over text highlights the words it touches;
- a click anywhere clears the highlight, including outside the page;
- the square handles resize the selected element;
- `Ctrl+A` selects all the text of the page, `Ctrl+C` copies.

Copied text keeps its formatting: pasted into a text editor it stays plain,
pasted into a spreadsheet or into Word it keeps the table.

---

## Annotations

### The tools

**Highlighters**: highlight, underline, strike out, squiggly. They are dragged
over the text: the height adjusts itself to the line.

**Shapes**: rectangle, ellipse, line, arrow, polygon, freehand ink. They are
drawn by dragging.

**Text and image**: text box (opens an editor with font, size, alignment,
colour, border, fill) and image (from a file or from the clipboard).

**Testo libero** (free text, `Annota ▸ Testo libero`) is an annotation, not a text
box: it can be moved, reopened, deleted, and it appears in the comments panel,
whereas a text box is burned into the page content. Bold, italic and underline
are chosen in the dialog that opens, or with the **B**, **I** and **U** levers
on the text toolbar.

**Nota** (note): a sticky note with an icon of your choice.

**Timbro** (stamp): a text stamp in the shapes provided.

**Collegamento** (link): you draw a box and type the address.

**Redazione** (redaction): permanently covers the chosen text, which disappears
from the file. You drag a rectangle over the words to remove; the program asks
for confirmation, because the operation is permanent and does not undo with the
rectangle.

**Allega file** (attach file): attaches any file to the PDF.

### Editing an annotation

A click selects it, the handles resize it, dragging moves it. The context menu
offers properties, copy, delete.

If there is both an annotation and a link under the cursor, the annotation
wins: the link only opens where there is nothing else to grab. With the drawing
tools a click follows the link only when the select tool is active, so you can
draw over a link.

*Annota ▸ Appiattisci annotazioni* (Flatten annotations) burns them into the
page content: from that moment they are no longer editable. It is the way to
send someone a PDF that cannot be altered any more.

**Image properties**: with the Image tool selected, *Proprietà immagine* opens a
window with width and height in points, an option to keep the aspect ratio and
one to crop the part that goes off the page. It applies to every image already
present, not only to newly inserted ones.

### Colours and styles

*Annota ▸ Stile annotazione* chooses colour, width, fill and opacity for shapes.
*Annota ▸ Stile evidenziazione* for the highlighters. The choices apply to
subsequent annotations.

---

## Forms

### Filling

With highlighting on, every field is outlined in blue. A click inside a field
opens the editor in the right place and writes into the document as you type.

Fields with a drop-down are chosen from, checkboxes are ticked, radio buttons
are selected.

`Tab` moves to the next field.

### New fields

*Moduli ▸ Campo di testo* (and checkbox, radio button, drop-down, push button)
puts the tool in your hand: a click on the page creates the field with a
sensible default size. Drag to choose the measurements.

Properties open with a double click on the field: name, value, font, size,
colour, opacity, tooltip, required, read-only, maximum length.

### Existing but undeclared fields

*Strumenti ▸ Rileva campi e moduli* (Detect fields) turns the empty boxes a
producer drew by hand into real fields: they can then be filled and saved.

### Filling in sequence

*Moduli ▸ Compila tutti i campi vuoti* (Fill all empty fields) opens the fields
one after another, useful for a long form.

### Resetting and flattening

*Annota ▸ Azzera campi* (Reset fields) returns everything to its initial value.
*Annota ▸ Appiattisci campi* (Flatten fields) turns the fields into fixed text:
the form is no longer fillable, the text stays.

---

## Signatures

### Creating a signature

*Firma ▸ Inserisci firma…* or `Ctrl+Shift+G`, or the Firma (Signature) tool: a
click on the page opens the dialog with the signature already positioned where
you clicked.

The dialog has four tabs.

**Disegna** (Draw) — sign with the mouse or a finger. With a stylus, the
pressure changes the stroke width.

**Tastiera** (Keyboard) — type the name and choose among the fonts found on the
system, with colour, size and slant.

**Immagine** (Image) — load a file or paste from the clipboard. There is
automatic background removal too, with brush, tolerance, threshold and edge
blur, to lift a signature off a photographed page.

**Libreria** (Library) — signatures already saved, with renaming and deletion.

### The placement options

Under the tabs:

- **Pagina** (Page): which page to put it on;
- **Dimensione** (Size): width and height in points;
- **Opacità** (Opacity): from 10% to 100%;
- **Appiattisci su bianco** (Flatten onto white): the signature is burned into
  the content instead of staying on top;
- **Campo firma** (Signature field): if the document has one, the signature is
  written inside its box and the field takes that value.

### Library

*Firma ▸ Libreria delle firme…* (Signature library) saves a signature with a
name and makes it reusable. *Firma ▸ Tutte le firme salvate* (All saved
signatures) lists them in the menu and inserts them with one click.

Saved signatures live in `~/.local/share/korvaxoide-pdf-editor/firme/`.

---

## Digital signatures

*Firma ▸ Firma digitale (certificato)…* (Digital signature).

You need a certificate in PKCS#12 format (`.p12` or `.pfx`). Choose the file,
type the password, and sign:

- the whole document, or
- a signature field, if the form has one.

The result is a valid signature: the document can no longer be modified without
invalidating it.

**To verify:** *Moduli ▸ Verifica firma digitale* (Verify digital signature)
shows the outcome, signer, issuer and date of each signature found.
*Strumenti ▸ Verifica firme…* (Verify signatures) does the same for the whole
document.

---

## Search and replace

### Finding

`Ctrl+F`. Type in the box and press `Enter` for the next result, `Shift+F3` for
the previous one. The page is brought into view on its own and the position is
highlighted.

Options: match case, and whole words (which excludes "ore" inside "Lorem").
Search takes the text literally: `(` looks for a parenthesis, not for a regular
expression.

### Replacing

`Ctrl+H` opens the replace. Say what to look for and what to put in its place,
and choose between replacing one, the next, the previous, or all.

Replacing **rewrites the page**: the word found is covered and the new one
written in its place, with the same size and the same position. The text is
not moved and the reading order stays what you see.

Replacements are undone with `Ctrl+Z` like any other change.

---

## Text recognition

*Strumenti ▸ OCR (riconosce testo)…* (Text recognition).

It needs `tesseract` with the Italian language (`tesseract-ocr-ita`).

Recognition adds an invisible text layer to the pages: the text becomes
selectable and searchable, but its appearance does not change.

It suits scans and photographs of printed documents.

---

## Protection

*Strumenti ▸ Proteggi documento…* (Protect document).

You can set:

- **password to open**: needed to read the document;
- **password to modify**: without it the document opens read-only;
- **permissions**: print, copy, modify, annotate, fill forms, extract pages
  and images.

Protection is applied to a **copy** of the document, called `nome_protetto.pdf`
next to the original, which stays as it was.

*Rimuovi protezione* (Remove protection) removes the encryption: it asks for the
owner password.

The program never loses encryption quietly: saving a protected document without
the passwords is refused, and you are told so.

---

## Exporting and converting

### File ▸ Esporta… (Export)

Choose what you want:

- **PDF**: another copy, optionally only some pages or with protection;
- **Immagini** (Images): PNG or JPEG, one per page, at the resolution you want;
- **Testo** (Text): the text of the whole document or of one page;
- **HTML**: to put the document on the web.

### File ▸ Importa da immagini… (Import from images)

Turns a set of images (JPEG, PNG, TIFF, BMP, WebP) into a PDF, in the order
they are selected.

### File ▸ Unisci documenti… (Merge documents)

Joins several PDFs into one, in the order you choose, with the option to insert
some pages from each document.

### File ▸ Dividi documento… (Split document)

Splits the PDF into parts, choosing where: every N pages, into a fixed number
of parts, at an exact point, or by extracting a range.

### Printing

`Ctrl+P`. Choose the printer, the page range, the number of copies and the
orientation.

### PDF/A

Inside *File ▸ Esporta…*, choosing the PDF format and the PDF/A level. It needs
`ghostscript`; when finished, the program checks the result and tells you
whether the conversion succeeded.

---

## Document quality

### The Quality panel

The **Qualità** (Quality) tab of the side panel examines the file and reports:

- fonts that are not embedded (the text may look different elsewhere);
- very large images (which weigh the file down);
- metadata that says more than it should (author, program that created the
  file);
- annotations and fields that are still editable;
- hidden objects;
- external links.

Each entry says what to do and, where possible, has a button that fixes it.

### Reduce size

*File ▸ Riduci dimensione del file…* (Reduce file size)

The program lists the images with their size and weight, and shows how much
would be saved. You choose the quality and the maximum resolution.

Before and after appear side by side, with the saving in percentage.

---

## Attachments and comments

**Attachments** — *Annota ▸ Allega file…* attaches a file to the PDF. The
**Allegati** panel lists them, lets you open them and remove them.

**Comments** — the panel lists the annotations that carry text: notes, text
boxes, stamps. You can search among the comments, filter them by type and jump
to the one you want on the page.

---

## Bookmarks

The **+** button in the **Segnalibri** (Bookmarks) panel (or a double click on
a bookmark itself) creates a bookmark at the current page, with the name you
want.

In the panel you can:

- rename (double click on the name);
- move up and down to reorder;
- group with the levels;
- delete;
- jump to a page with one click.

---

## External programs

| Program | Used for | When absent |
| --- | --- | --- |
| `tesseract` | OCR | the entry is greyed out and explains why |
| `ghostscript` (`gs`) | PDF/A | the entry is greyed out and explains why |

On Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-ita ghostscript
```

On Fedora: `sudo dnf install tesseract tesseract-langpack-ita ghostscript`

Tesseract can also be installed without administrative rights, in the user's
own directory: `run.sh` adds `~/.local/bin` to `PATH`, so copying the
executable there is enough.

---

## Frequent problems

**"I can't see the dialog's options"**
Every dialog fits itself to the screen and the content scrolls. If there is
little room, make the main window smaller.

**"A field looks out of place"**
The view shows the page scaled: field highlighting helps you see where they
are. If a field looks displaced, save and reopen the document.

**"I can't move a field"**
You need **Alt+click**: a plain click opens the editor to type into it.

**"The signature has vanished or is in the wrong place"**
A signature is an object like any other: with the *Seleziona* tool, click and
drag it. If you cannot see it, look at *Visualizza ▸ Presentazione*: the
signature is placed at the centre of what is on screen, so it shows at once.

**"The typed signature is a row of little squares"**
The chosen font has no letters. In the list, fonts that have them are at the
top; those that do not are at the bottom and say so.

**"The dark theme is incomplete"**
If a dialog opened before the change stays light, close it and reopen it:
dialogs take the active theme when they are created.

**"The button is gone"**
*Visualizza ▸ Pannelli laterali* (`Ctrl+Shift+L`) and *Pannello pagine*
(`Ctrl+Shift+P`).

**"I lost my work"**
The notice at start-up offers the recovery copy. The program saves one after
each change.

**"I can't save a protected document"**
That is the intended behaviour: saving a protected PDF without the passwords
would produce an unprotected file. Use *File ▸ Salva una copia…* and then
*Strumenti ▸ Proteggi documento…*.

**"The signature will not go in"**
Check that the chosen tab has something in it: a drawn scribble, a typed name, a
loaded image or a signature from the library. With no content the *Inserisci*
button does nothing and says so.

**"The PDF/A is not produced"**
It needs Ghostscript, which is installed separately. It is in *File ▸ Esporta…*,
choosing "PDF/A (archiviazione)" as the format and the PDF/A level: it is not a
menu entry of its own.