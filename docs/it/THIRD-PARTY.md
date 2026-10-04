# Crediti e licenze di terze parti

> **Lingua:** Italiano · [English](../../THIRD-PARTY.md)

Korvaxoide PDF Editor è software libero rilasciato sotto **GNU AGPL-3.0** (vedi
[LICENSE](../../LICENSE)). Tutto il codice di `pdfeditor/`, `tools/`, `tests/` e degli
script di compilazione è originale di questo progetto.

## Perché la licenza è AGPL-3.0

Il motore PDF è **PyMuPDF**, che è dual-licensed: **GNU AGPL-3.0** oppure una
licenza commerciale di Artifex. Finché non si acquista quella licenza
commerciale, l'intera applicazione è necessariamente AGPL-3.0: l'AGPL è una
licenza copyleft forte e si applica all'opera nel suo complesso.

**Il programma non può essere rilasciato con una licenza permissiva** (MIT,
BSD, Apache…) finché dipende da PyMuPDF. Le alternative sono:

1. acquistare una licenza commerciale di Artifex ([pymupdf.com](https://pymupdf.com/commercial/)),
   e a quel punto rilasciare l'applicazione con la licenza che si preferisce;
2. sostituire PyMuPDF con una libreria permissiva, che richiederebbe di
   riscrivere profondamente il nucleo (PyMuPDF è usato per rendering, campi
   modulo, annotazioni, redazione, OCR e firma digitale).

Se in futuro la licenza cambiasse, andrebbero rimossi i riferimenti ad AGPL in
questo file, nel README e nelle intestazioni dei sorgenti.

## Dipendenze

### Runtime

| Pacchetto | Versione | Licenza | Uso |
|---|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | 1.28.2 | **AGPL-3.0** (o commerciale Artifex) | Motore PDF: rendering, annotazioni, campi, testo, redazione |
| [PySide6](https://doc.qt.io/qtforpython/) (Qt 6) | 6.11.2 | LGPL-3.0 (anche GPL-2.0/3.0) | Interfaccia grafica |
| [Pillow](https://python-pillow.org/) | 12.3.0 | MIT-CMU | Immagini, rendering e rimozione dello sfondo |
| [NumPy](https://numpy.org/) | 2.5.3 | BSD-3-Clause | Calcolo per la rimozione dello sfondo e l'analisi delle immagini |
| [cryptography](https://cryptography.io/) | 50.0.1 | Apache-2.0 **o** BSD-3-Clause | Chiavi e operazioni crittografiche per la firma digitale |
| [asn1crypto](https://github.com/wbond/asn1crypto) | 1.5.1 | MIT | Lettura e scrittura del CMS (PKCS#7) |

### Strumenti di compilazione

| Pacchetto | Licenza | Uso |
|---|---|---|
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0 **con eccezione** | Compilazione dell'eseguibile autonomo |

L'eccezione di PyInstaller autorizza esplicitamente a includere il proprio
codice in applicazioni proprietarie e non copyleft: la compilazione non
introduce obblighi sulla licenza di Korvaxoide PDF Editor.

### Programmi esterni opzionali

Non sono richiesti per usare l'applicazione; se assenti, le funzionalità
corrispondenti restano semplicemente non disponibili.

| Programma | Licenza | Funzione |
|---|---|---|
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | Riconoscimento del testo nelle scansioni |
| [Ghostscript](https://www.ghostscript.com/) | AGPL-3.0 | Conversione in PDF/A |

Ghostscript è un programma esterno invocato come subprocesso e non viene
collegato né ridistribuito: il suo uso è soggetto alla propria licenza.

## Font

Nessun font è incluso in questo repository. I font usati per il rendering
provengono dal sistema e restano proprietà dei rispettivi autori:

- **DejaVu** — Bitstream Vera / DejaVu licence (permissiva)
- **Liberation** — SIL Open Font License 1.1
- i font base 14 (Helvetica, Times, Courier, Symbol, ZapfDingbats) non sono
  incorporati nei PDF prodotti: sono presenti in ogni lettore

## Risorse grafiche

Le icone dell'applicazione (`resources/icons/`) e il file `.desktop` sono
generati dal codice di questo progetto (`tools/make_icons.py`,
`resources/korvaxoide-pdf-editor.desktop`) e non contengono materiale di terzi.

## Codice di terze parti nel repository

Nessuno. Non è presente codice copiato o adattato da altri progetti.

## Ringraziamenti

Questo progetto si regge su software libero straordinario. In particolare:

- **Artifex** per PyMuPDF e MuPDF, che rendono possibile la parte difficile:
  interpretare e scrivere PDF senza reinventare nulla;
- **Qt Project** per Qt 6 e PySide6;
- **Haaikeli** per Pillow, **NumPy** per NumPy, **pyca/cryptography** per
  `cryptography` e **wbond** per asn1crypto;
- **Ubuntu** per Tesseract e **Artifex** per Ghostscript.
