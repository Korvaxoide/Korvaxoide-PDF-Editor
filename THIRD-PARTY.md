# Third-party credits and licences

> **Language:** English · [Italiano](docs/it/THIRD-PARTY.md)

Korvaxoide: PDF Editor is free software released under the **GNU AGPL-3.0** (see
[`LICENSE`](LICENSE)). All the code in `pdfeditor/`, `tools/`, `tests/` and the
build scripts is original to this project.

## Why AGPL-3.0

The PDF engine is **PyMuPDF**, which is dual-licensed: **GNU AGPL-3.0** or a
commercial licence from Artifex. Unless that commercial licence is bought, the
whole application is necessarily AGPL-3.0: the AGPL is a strong copyleft and it
applies to the work as a whole.

**The program cannot be released under a permissive licence** (MIT, BSD,
Apache…) while it depends on PyMuPDF. The alternatives are:

1. buy the commercial licence from Artifex
   ([pymupdf.com](https://pymupdf.com/commercial/)), and then release the
   application under whichever licence you prefer;
2. replace PyMuPDF with a permissive library, which would mean rewriting the
   core deeply: PyMuPDF is used for rendering, form fields, annotations,
   redaction, OCR and digital signatures.

If the licence ever changes, every reference to the AGPL in this file, in the
README and in the source headers has to be removed.

## Dependencies

### Runtime

| Package | Version | Licence | Used for |
|---|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | 1.28.2 | **AGPL-3.0** (or Artifex commercial) | PDF engine: rendering, annotations, fields, text, redaction |
| [PySide6](https://doc.qt.io/qtforpython/) (Qt 6) | 6.11.2 | LGPL-3.0 (also GPL-2.0/3.0) | Graphical interface |
| [Pillow](https://python-pillow.org/) | 12.3.0 | MIT-CMU | Images, rendering, signature background removal |
| [NumPy](https://numpy.org/) | 2.5.3 | BSD-3-Clause | Computation for background removal and image analysis |
| [cryptography](https://cryptography.io/) | 50.0.1 | Apache-2.0 **or** BSD-3-Clause | Keys and cryptographic operations for digital signatures |
| [asn1crypto](https://github.com/wbond/asn1crypto) | 1.5.1 | MIT | Reading and writing CMS (PKCS#7) |

### Build tools

| Package | Licence | Used for |
|---|---|---|
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0 **with a exception** | Building the self-contained executable |

PyInstaller's exception explicitly allows your own code to be included in
proprietary, non-copyleft applications, so the build introduces no licensing
obligation on Korvaxoide: PDF Editor.

### Optional external programs

They are not needed to use the application; when absent, the corresponding
features are simply unavailable.

| Program | Licence | Function |
|---|---|---|
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | Text recognition in scans |
| [Ghostscript](https://www.ghostscript.com/) | AGPL-3.0 | PDF/A conversion |

Ghostscript is an external program invoked as a subprocess and is neither
linked nor redistributed: its use is subject to its own licence.

## Fonts

No font is included in this repository. The fonts used for rendering come from
the system and remain the property of their respective owners:

- **DejaVu** — Bitstream Vera / DejaVu licence (permissive)
- **Liberation** — SIL Open Font License 1.1
- the base 14 fonts (Helvetica, Times, Courier, Symbol, ZapfDingbats) are not
  embedded in the PDFs the program produces: they are present in every reader

## Graphics resources

The application icons (`resources/icons/`) and the `.desktop` file are generated
by this project's code (`tools/make_icons.py`, `resources/korvaxoide-pdf-editor.desktop`)
and contain no third-party material.

## Third-party code in the repository

None. No code copied or adapted from other projects is present.

## Acknowledgements

This project stands on outstanding free software. In particular:

- **Artifex** for PyMuPDF and MuPDF, which make the hard part possible:
  interpreting and writing PDFs without reinventing everything;
- **Qt Project** for Qt 6 and PySide6;
- **Haaikeli** for Pillow, **NumPy** for NumPy, **pyca/cryptography** for
  `cryptography` and **wbond** for asn1crypto;
- **Ubuntu** for Tesseract and **Artifex** for Ghostscript.