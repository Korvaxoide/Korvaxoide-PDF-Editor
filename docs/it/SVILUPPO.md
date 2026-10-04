# Sviluppo di Korvaxoide PDF Editor

> **Lingua:** Italiano · [English](../../CONTRIBUTING.md)

Come è organizzato il codice, come si verifica e come si rilascia.

---

## Indice

1. [Ambiente](#ambiente)
2. [Struttura del codice](#struttura-del-codice)
3. [Regole di progetto](#regole-di-progetto)
4. [Verifiche](#verifiche)
5. [Aggiungere una funzionalità](#aggiungere-una-funzionalità)
6. [Risoluzione dei problemi](#risoluzione-dei-problemi)
7. [Rilascio](#rilascio)
8. [Licenza](#licenza)

---

## Ambiente

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m pdfeditor
```

Serve Python 3.12 o successivo. Le dipendenze sono in `requirements.txt`.

Per i controlli servono anche:

```bash
./venv/bin/pip install pytest
```

Programmi esterni opzionali: `tesseract` (OCR) e `ghostscript` (PDF/A). Senza
non fallisce nulla: le voci di menu corrispondenti diventano grigie e
spiegano il motivo.

---

## Struttura del codice

```
pdfeditor/
  __init__.py          nome, versione, identificativi
  __main__.py          punto d'ingresso per «python -m pdfeditor»
  app.py               avvio: ambiente, traduttore, QApplication
  core/                il motore PDF, senza interfaccia
    document.py        pagine, annotazioni, campi, testo, immagini, sicurezza
    geometry.py        rettangoli, rotazioni, intersezioni, aggancio
    settings.py        preferenze su disco (JSON)
    textlayout.py      misura del testo e impaginazione
    units.py           formati pagina e unità
    errors.py          eccezioni del dominio
  ui/                  l'interfaccia
    main_window.py     finestra, menu, barre, azioni
    page_view.py       vista a scorrimento e strumenti di disegno
    page_items.py      nodi di pagina, campi, selezione
    panels.py          pannelli laterali
    thumbnails.py      miniature delle pagine
    dialogs/           finestre di dialogo
    printing.py        stampa ed esportazione
    theme.py           colori, misure, foglio di stile
    icons.py           disegno delle icone
    ocr.py             riconoscimento del testo
  features/            qualità del documento, firma digitale
  signature/           libreria, disegno e rendering delle firme
tests/
  test_document.py     il motore PDF
  test_ui.py           l'interfaccia
  test_interazione.py  eventi reali sulla finestra
  test_funzionalita.py ogni funzionalità, una per una
  test_dialoghi.py     ogni dialogo si apre e sta nello schermo
  conftest.py          fixture condivise
  integration.py       flussi completi
  finale.py            collaudo
  visual.py            catture dell'interfaccia
tools/
  make_icons.py        genera le icone (non sono nel repository)
resources/
  korvaxoide-pdf-editor.desktop   voce per il menu delle applicazioni
```

---

## Regole di progetto

### Il motore non conosce l'interfaccia

`core/` non importa nulla di `ui/`. Tutto ciò che l'interfaccia può chiedere al
documento è un metodo pubblico di `Document`.

### Ogni modifica passa da `_mutate`

```python
def _mutate(self, testo, fn, result_index=-1, emit_pages=False):
    before = self.snapshot() if self._undo_enabled else b""
    try:
        out = fn()
    except Exception:
        if before:
            self._restore(before)      # un'operazione fallita non lascia spazzatura
        raise
    if before and self._undo_enabled:
        self.history.run(SnapshotCommand(self, testo, before, self.snapshot()))
    ...
```

Chi scrive direttamente sulle pagine salta l'annullamento: è così che la
sostituzione di testo ha perso il testo senza poter essere annullata, e che
«Cambia dimensione pagina» non si poteva disfare con `Ctrl+Z` finché non è
diventato il metodo pubblico `Document.set_page_size`.

La closure passata a `_mutate` **deve restituire un valore** se il metodo
riporta un esito: `bool(self._mutate(...))` su una closure che non restituisce
niente dà sempre `False`, e un chiamante che controlla il risultato legge «non
riuscito» anche quando è andato tutto bene.

### Le coordinate di scena sono in punti

La scala la fa la trasformazione della vista (`set_zoom` chiama `setTransform`).
Il codice che converte fra spazio pagina e spazio di scena usa i tre
metodi di `PdfView`:

- `_scene_rect(pagina, rect)` — per la pagina verso la scena;
- `_scene_point(pagina, punto)`;
- `_page_local(pagina, punto_scena)` — per tornare indietro.

Nessuno di questi moltiplica per lo zoom. Farlo è stato un bug: a 200% ogni
elemento finiva fuori posto, perché lo zoom veniva applicato due volte.

Le conversioni inverse passano da `Document.to_display_rect` e
`Document.to_page_rect`, che tengono conto della rotazione del PDF e di quella
della vista.

### Gli attributi non nascondono i metodi di QWidget

`QWidget` ha i metodi `size()`, `width()`, `height()`, `font()`, `rect()`,
`palette()`. Assegnare un attributo con lo stesso nome li rende irraggiungibili
da Python: un `dialogo.size()` su un dialogo che ha `self.size = QSpinBox()`
solleva un errore. I controlli dei dialogi hanno nomi propri
(`size_box`, `width_box`, `font_box`).

### I dialogi si adattano allo schermo

Ogni dialogo chiama `dlgutil.adatta_a_schermo(self, larghezza, altezza)` all'inizio
del costruttore. La funzione:

1. riduce la dimensione a quella disponibile;
2. se il contenuto minimo non entra, lo mette in un'area scorrevole.

Senza questo, su uno schermo piccolo i pulsanti finiscono fuori vista e la
funzione sembra non funzionare.

### Il tema si propaga da solo

`theme.attiva(pal)` imposta la palette in uso e `theme.corrente()` la restituisce.
Le finestre e i pannelli la leggono quando si costruiscono (`self.palette =
theme.corrente()`), così non vanno informati uno a uno quando cambia il tema. Chi
disegna a mano riceve invece `set_palette_colors`, chiamato da
`MainWindow._apply_theme` per tutti i pannelli.

### I font si scelgono per copertura, non per nome

`typed.list_fonts()` ordina i font in base ai glifi che contengono davvero
(`ha_lettere`), non in base a cosa dice il nome del file: molti font con
«script» nel nome coprono una scrittura antica e il testo esce come una fila
di rettangoli.

### Le azioni dei menu vanno tenute vive

In PySide6 un `QAction` senza riferimenti Python viene raccolto e sparisce dal
menu. `MainWindow._azioni_menu` li conserva tutti. E vanno creati **senza**
passare `None` come icona:

```python
# sbagliato: con l'icona None PySide6 sceglie l'overload sbagliato e
# l'azione nasce senza testo
a = QAction(None, testo, self)

# giusto
a = QAction(testo, self)
if icona:
    a.setIcon(icons.icon(icona, ...))
```

Le scorciatoie stanno **solo** nei menu. Se anche la barra le definisce, Qt le
segnala come ambigue e le ignora.

### L'aiuto alle scorciatoie si ricava dai menu

`MainWindow._elenco_scorciatoie()` legge le scorciatoie dalle voci di menu e
costruisce l'elenco. Una volta l'elenco era scritto a mano e promise cose che il
programma non accettava: «Ctrl+G» per la griglia (che era `Ctrl+'`), i tasti da
una lettera per gli strumenti (mai registrati) e `Ctrl+W` per chiudere (azione
che non è mai esistita). Un elenco scritto a mano si allontana sempre da
quello che il programma fa; questo non può.

### I tasti da una lettera sola non si registrano

I campi modulo si compilano dentro la finestra principale, quindi hanno lo
stesso contesto di scorciatoie: una scorciatoia `V` sulla finestra scatterebbe
la digitazione nei campi. Per questo V/H/T/S/I sono un richiamo nei suggerimenti
e non scorciatoie, e l'aiuto non le elenca.

### Un'icona disegnata a mano non può fallire in silenzio

`icons._disegna()` avvisa con un `RuntimeWarning` se il disegno solleva. Prima
l'errore veniva inghiotito: `Qt.RashCap` al posto di `Qt.RoundCap` faceva
sparire del tutto l'icona dello strumento predefinito, e in barra c'era un
quadrato vuoto senza diagnosi. `test_ui.py` disegna tutte le icone e verifica
che non escano vuote e che prendano il colore del tema.

### PyMuPDF gonfia il riquadro delle annotazioni

`annot.rect` restituisce il `/Rect` con dentro il bordo, e `set_rect` scrive il
`/Rect` allargato di `max(bordatura, 2) / 2` per lato. Riscrivere il valore
letto gonfiava l'annotazione di due punti a ogni spostamento: un rettangolo da
100×60, trascinato quattro volte, arrivava a 110×70. `Document._rect_come_lettorlo`
defila il riquadro prima di scriverlo, e `test_document.py` verifica che le
dimensioni restino costanti.

### Un nome che si ricava da una stringa non è un nome

Lo strumento «Casella di spunta» si chiamava `field_check` e il codice ne
tirava fuori il tipo con `tool.replace("field_", "")`, arrivando a `check`: un
nome che in `WIDGET_TYPES` non esiste. Ogni casella di spunta moriva con «Tipo
di campo non supportato: check». La corrispondenza ora è la tabella
`main_window.FIELD_TOOLS`, e vale la regola generale: **se un nome viene
ricavato da una stringa, va cercato in una tabella, non con una sostituzione**.

Lo stesso vale per le coppie delle finestre: nei dialoghi del font la coppia
era al contrario (si mostrava il codice interno e si conservava il nome
esteso), `findData` non trovava nulla, la combinazione restava vuota e i
valori riportavano la stringa `"None"`. Il font scelto per un campo finiva
sempre in Helvetica.

### Un'opzione offerta deve cambiare qualcosa

Tre esempi, tutti trovati esercitando l'interfaccia:

- «Parola intera» confrontava `needle in testo`, cioè una sotto-stringa:
  tornava sempre vero e «ore» trovava anche dentro «Lorem».
- La sostituzione non riceveva `case` e `whole_word` dalla finestra di
  ricerca: le due caselle non avevano effetto quando si sostituiva.
- «Qualità JPEG» arrivava a `extract_page_image` senza il parametro, e la
  levetta `B`/`I`/`U` scriveva solo un messaggio.

Quando una finestra raccoglie un'opzione, va passata al motore, e il motore
la deve usare. Meglio ancora: se un parametro pubblico non serve a nulla,
si toglie, così non promette niente (`_mutate(result_index=…)`,
`hide_field_editor(commit=…)`).

### Le finestre che si aprono vanno provate con valori veri

Un controllo che costruisce ogni dialogo e lo chiude con `reject` verifica
solo che la finestra si apra. Con `accept` e valori plausibili si esercita
anche tutto quello che segue, ed è lì che stanno i difetti. Vale anche per
gli intervalli: `parse_range` deve rispondere a `1-`, `-2`, `abc` e `1-99`,
e un intervallo illeggibile deve essere un errore detto, non una lista vuota
che il chiamante sostituisce con la pagina corrente.

### Sotto il cursore vince ciò che si vede in alto

La prova del collegamento veniva prima di ogni altra nel clic, e vinceva
sempre: un'annotazione appoggiata su un collegamento non si poteva
selezionare, spostare, ridimensionare o cancellare, e con gli strumenti di
disegno il clic apriva il browser invece di disegnare. L'ordine corretto è:
maniglie, campi, annotazioni e immagini, **poi** il collegamento, e il
collegamento si prova solo con lo strumento di selezione.

### Una dipendenza che non si importa è un peso inutile

`reportlab` e `pikepdf` erano in `requirements.txt`, in `THIRD-PARTY.md`,
nella finestra delle licenze e controllati dalla CI, ma il programma non li
importava mai. Ora la CI ha un passo che verifica il contrario: ogni
dipendenza dichiarata deve comparire fra gli import di `pdfeditor/`. E le
dipendenze facoltative (scipy, per la rimozione dello sfondo) si dichiarano
come facoltative, non come requisite.

### Spostare un'immagine non è cancellarla e reinserirla

`Document.move_image` rilegge l'immagine e la reinserisce, perché le immagini
non sono annotazioni e non si possono spostare da sole. Ma MuPDF, quando
cancella un'immagine, ne lascia al posto un segnaposto di un pixel: alla
seconda mossa la nuova immagine finiva su quel segnaposto e **spariva dal
file**. Con una firma inserita dal programma voleva dire che trascinare due
volte la faceva svanire.

La riapertura del documento dai suoi stessi byte fra la cancellatura e la
reinserimento ricostruisce il dizionario delle risorse e risolve. Costa una
serializzazione, che il progetto paga già a ogni modifica.

Due conseguenze da tenere a mente: `image_rects` deve scartare i segnaposto
(un'immagine di un pixel non è un'immagine del documento, ma finiva
nell'inventario e sotto il cursore), e lo `xref` dell'immagine cambia a ogni
spostamento, quindi chi tiene una selezione deve ricalcolarla.

### La documentazione non può promettere più di quanto fa il programma

Il manuale prometteva una ricerca con «caratteri speciali» (espressioni
regolari: `search_for` cerca il testo alla lettera), tre punti della pagina
per la numerazione (sono tre punti del piè), una scorciatoia scritta male
(`Maiusc+Invò`) e un'esportazione in HTML che non esiste. Se una correzione
cambia il comportamento, la riga di documentazione si corregge con lei.

### Ogni icona e ogni voce di menu si ricostruiscono quando cambia il tema

Le icone sono disegnate a mano e prendono il colore dalla palette, quindi
`MainWindow._apply_theme` chiama `toolbars.refresh_icons`. I colori delle
maniglie di ridimensionamento stanno nella `Palette` e non nelle `Metrics`: con
i colori fissi sul tema chiaro restavano bianche anche a tema scuro.

---

## Verifiche

```bash
./venv/bin/python -m pytest tests/ -q         # tutto
./venv/bin/python -m pytest tests/test_funzionalita.py -q
./venv/bin/python -m pytest tests/test_dialoghi.py -q
./venv/bin/python -m pytest tests/test_interazione.py -q
./venv/bin/python -m pytest tests/test_documentazione.py -q
./venv/bin/python tests/integration.py
./venv/bin/python tests/finale.py
./venv/bin/python tests/visual.py
```

Su una sola piattaforma i problemi di layout sfuggono. La suite di interazione
va eseguita anche sulla sessione grafica vera:

```bash
unset QT_QPA_PLATFORM
XDG_SESSION_TYPE=wayland ./venv/bin/python -m pytest tests/test_interazione.py -q
```

### I test non scrivono nei dati dell'utente

`tests/ambiente.py` sposta configurazione e dati in una cartella temporanea
prima di qualunque import del programma, e va chiamato **prima di tutto**,
anche dagli script a sé stanti:

```python
import ambiente

ambiente.configura_qt()
ambiente.isola()
ambiente.prepara_percorso()
```

Senza questo la suite scriveva nelle preferenze vere e costruiva una libreria
firme sull'utente: un test che cambiava il tema o disattivava il recupero
lasciava il programmo con impostazioni diverse da quelle aspettate, e la cosa
si scopriva solo alla verifica successiva, riavviando l'applicazione.

Le cartelle sono calcolate a ogni chiamata leggendo le variabili d'ambiente,
quindi basta spostarle: non serve alcun punto di aggancio nel codice.

### I test devono passare anche su Windows

La suite gira su Linux e su Windows, e un test che passa su un sistema e
fallisce sull'altro è un difetto del test, non della macchina. Due famiglie di
presupposti hanno causato quasi tutti quelli trovati:

- **Percorsi che esistono solo su un sistema.** `/tmp/...`,
  `/usr/share/fonts/...` e `/bin/true` su Windows non ci sono, e un errore di
  permessi sollevato dal sistema operativo non è una proprietà del programma.
  I file temporanei passano da `ambiente.cartella(...)` e
  `ambiente.ricrea(...)`, che danno una cartella dentro quella che la suite ha
  già isolato; i test che hanno bisogno di un percorso inutilizzabile lo
  costruiscono mettendo un file dove dovrebbe stare una cartella.
- **Font che esistono solo su un sistema.** Una firma disegnata con un font non
  installato non fallisce: esce vuota o piena di quadratini, e il test che
  controlla solo che il file sia stato scritto non se ne accorge.
  `ambiente.font_serif()` restituisce un font che c'è davvero, e un test che ne
  ha bisogno salta spiegandolo quando non ce ne sono.

La regola vale anche per gli script a sé stanti: girano in CI come la suite,
quindi prendono font e cartelle da `ambiente`.

### Cosa coprono le verifiche

| File | Cosa verifica |
| --- | --- |
| `test_document.py` | il motore PDF, riga per riga |
| `test_security.py` | firma digitale, cifratura e permessi |
| `test_signature.py` | tratti, rendering e rimozione dello sfondo |
| `test_quality.py` | i controlli di qualità e accessibilità |
| `test_core.py` | geometria, cronologia, unità, impaginazione |
| `test_ui.py` | finestre, pannelli, temi, icone |
| `test_interazione.py` | clic, tastiera e scorciatoie vere |
| `test_funzionalita.py` | ogni funzionalità, una alla volta |
| `test_dialoghi.py` | ogni dialogo si apre e sta nello schermo |
| `test_regressioni.py` | i difetti trovati esaminando il motore voce per voce |
| `test_regressioni_ui.py` | gli stessi difetti, con eventi veri del mouse |
| `test_documentazione.py` | collegamenti, ancore e file che i documenti citano |
| `integration.py` | flussi completi da capo a fondo |
| `finale.py` | collaudo dell'applicazione |
| `visual.py` | catture per il confronto a vista |

### Perché esercitare l'interfaccia e non solo i metodi

I difetti più gravi trovati finora non si vedono chiamando i metodi:

- i menu si svuotavano perché le azioni venivano raccolte;
- il riquadro azzurro dei campi non coincideva con l'input perché lo zoom era
  applicato due volte, una alla vista e una nelle conversioni;
- il riquadro di disegno della firma non accettava nessun tratto, per due
  `TypeError` diversi;
- la presentazione entrava ma non usciva;
- la firma finiva in un punto a caso e non la si poteva spostare, perché le
  immagini non erano cercate fra gli elementi afferrabili;
- la firma scritta a tastiera usciva come una fila di quadratini, per un font
  di scrittura antica scelto dal nome del file.

Una verifica che chiama `w.action_signature()` e guarda il valore di ritorno
passerebbe lo stesso. Servono gli eventi.

---

## Aggiungere una funzionalità

1. **Il motore**: un metodo pubblico su `Document` che usa `self._mutate(...)`.
2. **L'azione**: un metodo `action_…` su `MainWindow` che chiama il motore,
   usa `self._busy_start()` se è lento, `self._error(exc, "…")` in caso di
   problema e `self._status("…")` per dire cosa è successo.
3. **La voce di menu**: `self._mi(menu, "Testo", "Ctrl+K", self.action_…, "icona")`.
   Una sola scorciatoia, mai due.
4. **La verifica**: un test in `test_funzionalita.py` che la esegue davvero, e
   se ci sono finestre coinvolte anche in `test_interazione.py`.
5. **Il documento**: una riga nel README e nel manuale.

Una funzionalità non è finita finché non ha la verifica che la esercita.

---

## Risoluzione dei problemi

### Un'azione non fa nulla

La voce è disabilitata? Controllare `isEnabled()`. Poi verificare che il menu
sia stato ricostruito: le azioni nuove vanno aggiunte a `_azioni_menu`.

### Le coordinate non quadrano

Verificare che la conversione passi da `_scene_rect`/`_page_local` e che
`PageNode` non abbia una dimensione derivata dallo zoom: il nodo misura la
 pagina in punti, la scala la vista.

### Il disegno è sbagliato

Confrontare il confine disegnato con quello atteso, campionando i pixel
dell'immagine. Con un riferimento cromatico (il bordo bianco della pagina, un
blocco colorato) il confronto è valido su ogni piattaforma; con un bordo grigio
si confonde con l'antialiasing.

### Un dialogo si apre ma non si vede

Chiamare `dlgutil.adatta_a_schermo` e controllare `minimumSizeHint()` contro
l'altezza dello schermo.

### Il testo esce in ordine strano

`Page.insert_text` accoda il testo in fondo al flusso di contenuto: la
posizione è giusta ma l'ordine di lettura no. `Document.text()` riordina per
posizione, unendo i blocchi della stessa riga.

---

## Rilascio

1. Verifiche tutte verdi, anche su Wayland reale.
2. Aggiornare la versione in `pdfeditor/__init__.py`: è l'unico posto dove
   sta, e da lì viene letta dal nome dell'AppImage, dal nome dell'eseguibile
   Windows, dalla versione del pacchetto macOS e dalla finestra Informazioni.
   Il formato è `MAJOR.MINOR.PATCH` e un controllo lo verifica.
3. Aggiornare il conteggio dei test nel README.
4. Icone: `./venv/bin/python -m tools.make_icons`
5. Linux: `./build_linux.sh --onedir` (AppImage con `appimagetool`)
6. Windows: `.\build_windows.ps1`, che dà un file singolo. `-OneDir` dà invece la
   cartella portatile: pubblicala solo se è quello che vuoi, perché non è ciò
   che scarica la gente.
7. Aggiornare l'elenco delle licenze in `THIRD-PARTY.md`.
8. Commit con un messaggio che spieghi la causa, non solo il sintomo.
9. Tag git con la versione: `git tag -a v0.1.0 -m "Korvaxoide PDF Editor 0.1.0"`.

La versione `0.1.0` è la prima numerata: prima della versione era `1.0.0` di
default e non voleva dire niente, perché il programma non era mai stato
pubblicato.

---

## Licenza

AGPL-3.0-or-later. Vedi [`LICENSE`](../../LICENSE) e [`THIRD-PARTY.md`](../../THIRD-PARTY.md).

La licenza è imposta da PyMuPDF (AGPL). Chi vuole la licenza commerciale di
Artifex può comprarla e sostituire la libreria.
