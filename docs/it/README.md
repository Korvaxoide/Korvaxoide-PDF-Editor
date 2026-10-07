# Korvaxoide PDF Editor

> **Lingua:** Italiano · [English](../../README.md)

> **Questo file e' la traduzione del [README](../../README.md), che e' il testo
> di riferimento.** Le correzioni si fanno li' e poi si riportano qui.

Editor PDF per Linux e Windows, con firma, moduli e annotazioni.
Nessun documento lascia il computer: il programma non usa la rete.

![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)
![Qt](https://img.shields.io/badge/Qt-6-41cd52)
![Licenza](https://img.shields.io/badge/licenza-AGPL--3.0-8b5cf6)
![Test](https://img.shields.io/badge/test-815%20superati-4c1.svg)

---

## Indice

1. [Che cosa fa](#che-cosa-fa)
2. [Installazione](#installazione)
3. [Primo avvio](#primo-avvio)
4. [Funzionalità](#funzionalità)
5. [Scorciatoie da tastiera](#scorciatoie-da-tastiera)
6. [Dove finiscono i dati](#dove-finiscono-i-dati)
7. [Programmi esterni opzionali](#programmi-esterni-opzionali)
8. [Come è fatto il codice](#come-è-fatto-il-codice)
9. [Verifiche](#verifiche)
10. [Documentazione ulteriore](#documentazione-ulteriore)
11. [Licenza](#licenza)

---

## Che cosa fa

Korvaxoide PDF Editor è un editor di PDF completo: annota, compila moduli,
firma, cerca e sostituisce, riconosce il testo nelle scansioni, protegge il
documento e lo esporta in altri formati. Funziona su Linux e su Windows con
la stessa interfaccia.

Le caratteristiche che lo distinguono:

- **compila i moduli AcroForm** e li salva nelle PDF, non li stampa soltanto;
- **firma a mano, a tastiera, da immagine o da libreria**, con dimensione,
  opacità e appiattimento; una volta inserita è un oggetto come gli altri: si
  trascina e si ridimensiona;
- **firma digitale con certificato** (PKCS#12) e verifica delle firme presenti;
- **appiattisce annotazioni e campi** per rendere il documento non più
  modificabile;
- **redazione vera**: il testo coperto viene rimosso dal flusso, non soltanto
  coperto da un rettangolo nero;
- **riconosce il testo** (OCR) con Tesseract, se installato;
- **tema chiaro e scuro** per finestra, pannelli, finestre di dialogo ed editor;
- **controlla il documento prima di condividerlo**: font non incorporati,
  immagini enormi, metadati che parlano troppo;
- **riduce le dimensioni** ricomprimendo le immagini che ne fanno spese.

---

## Installazione

Tre modi per avviarlo, nell'ordine in cui li cerca la maggior parte delle
persone. Se il primo funziona, nel resto di questo README non serve altro.

### Scaricare l'eseguibile già pronto

Vai alla [pagina delle release](https://github.com/Korvaxoide/Korvaxoide-PDF-Editor/releases/latest)
e scarica il file del tuo sistema. Non c'è nulla da installare: il download è
un file solo che porta dentro Python e le librerie.

**Windows.** Il file si chiama `KorvaxoidePDF-<versione>.exe`, dove `<versione>`
è il numero nel titolo della release. Fai doppio clic e il programma parte.
Nessun installer, nessuna cartella, nient'altro da tenere accanto.

> **L'eseguibile non è firmato.** Su Windows 11 con Smart App Control attivo
> Windows avvisa che l'applicazione non è riconosciuta e offre *Ulteriori
> informazioni*. È il comportamento previsto: il progetto non ha un
> certificato di firma del codice, quindi l'avviso riguarda la firma che
> manca e non il programma. Scegli *Esegui comunque*. L'avviso è lo stesso che
> Windows mostra per qualunque programma non firmato.

**Linux.** Il file si chiama `KorvaxoidePDF-<versione>-x86_64.AppImage`:

```bash
chmod +x KorvaxoidePDF-<versione>-x86_64.AppImage
./KorvaxoidePDF-<versione>-x86_64.AppImage
```

`chmod +x` serve perché il permesso di esecuzione non sopravvive al download.
Nessuna installazione, nessun `sudo`, nessun Python.

Entrambi i file portano nel nome la versione, quindi i nomi da cercare sono
quelli elencati nella pagina delle release. Ogni release ha anche il link
*Source code*, che è il sorgente esatto di quel binario.

### Avviare dalla sorgente

Serve **Python 3.12 o successivo**: è il requisito di NumPy, e senza non si
possono installare le dipendenze.

Dipendenze (`requirements.txt`):

| Pacchetto | A cosa serve |
| --- | --- |
| PySide6 ≥ 6.11 | Interfaccia (Qt 6) |
| PyMuPDF ≥ 1.28 | Motore PDF |
| Pillow, NumPy | Immagini |
| cryptography, asn1crypto | Firma digitale |

Opzionale: **scipy** (BSD-3-Clause); se è installato migliora la rimozione dello
sfondo per le firme. Il programma funziona anche senza.

**Linux (Ubuntu).** Nessun `sudo`, nessuna modifica al sistema: tutto va in
`venv/`, dentro la cartella del progetto.

```bash
sudo apt install python3-venv      # solo se "python3 -m venv" non funziona
git clone https://github.com/Korvaxoide/Korvaxoide-PDF-Editor.git
cd Korvaxoide-PDF-Editor
./run.sh
```

`run.sh` crea `venv/` se manca, installa le dipendenze da `requirements.txt` e
avvia il programma. Con `./run.sh --solo` si ferma dopo aver preparato
l'ambiente.

Per avviarlo in seguito, e da qualunque cartella, si usa
`python3 -m pdfeditor` dentro la cartella che contiene `venv/`.

**Su Ubuntu 22.04** il `python3` di sistema è il 3.10 e l'ambiente non si può
costruire: installa `python3.12` e `python3.12-venv`, poi usa
`python3.12 -m venv venv`. Su Ubuntu 24.04 e successivi non serve nulla.

**Disinstalla:** cancella `venv/` e la cartella del progetto.

Non c'è uno script d'installazione. Avviare dalla sorgente è il modo
supportato, e questo significa niente voce nel menu delle applicazioni e
niente icone in `~/.local/share/icons/`. Se le vuoi, i pezzi sono ancora nel
repository: `venv/bin/python -m tools.make_icons` scrive `resources/icons/`, e
`resources/korvaxoide-pdf-editor.desktop` è una voce di menu già pronta che
punta a `run.sh`.

**Windows.** Serve Python 3.12 o successivo, installato dall'[installer
ufficiale](https://www.python.org/downloads/windows/) con l'opzione **Add
python.exe to PATH** spuntata. Estrarre la cartella e:

```bat
run.bat
```

`run.bat` prepara `venv\`, installa le dipendenze e avvia il programma; con
`run.bat --solo` installa senza avviare. Se sulla macchina ci sono più
versioni di Python e quella nel PATH è troppo vecchia, lo script lo dice e
propone `py -3.12`.

A mano, che è quello che fa `run.bat`:

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m pdfeditor
```

Su Windows non c'è uno script d'installazione: il programma resta nella
cartella e si avvia da lì. Per averlo nel menu, crea un collegamento a
`venv\Scripts\pythonw.exe` con come argomenti `-m pdfeditor` e come cartella
di lavoro la radice del progetto: `pythonw` non apre la console. Per aprivi
i PDF con un doppio clic va registrato
`HKCU\Software\Classes\Applications\pythonw.exe\shell\open\command`.

Il programma cerca i suoi programmi esterni anche in `~/.local/bin`: se
installi `tesseract` lì viene trovato senza configurare niente. Vedi
[Programmi esterni opzionali](#programmi-esterni-opzionali).

### Compilare un binario da soli

**Linux** (cartella singola e AppImage):

```bash
./build_linux.sh --onedir      # dist/KorvaxoidePDF/KorvaxoidePDF
./build_linux.sh               # anche AppImage (serve appimagetool)
```

**Windows** (PowerShell):

```powershell
.\build_windows.ps1            # dist\KorvaxoidePDF.exe, file singolo
.\build_windows.ps1 -OneDir    # cartella dist\KorvaxoidePDF\, portatile
```

Le icone non sono nel repository, sono disegnate: entrambi gli script le
generano prima di chiamare PyInstaller. Da sole:

```bash
./venv/bin/python -m tools.make_icons
```

Su Linux di default esce una cartella, perché l'AppImage si costruisce
impacchettando quella cartella; su Windows di default esce un file singolo,
che non ha bisogno di installer né di nulla accanto. La variabile
`KorvaxoidePDF_ONEDIR=1` o `=0` sceglie la struttura a mano su entrambi i
sistemi.

---

## Primo avvio

- **Aprire un documento:** doppio clic su un PDF, oppure il pulsante della cartella.
- **Aprire di recente:** *File ▸ Apri recente*.
- **Salvare:** `Ctrl+S`. *Salva come…* sceglie il percorso.
- **Non perdere nulla:** se si chiude con modifiche non salvate, il programma
  chiede cosa fare. *Recupera* all'avvio propose l'ultima copia.

Le impostazioni si trovano in *Strumenti ▸ Preferenze*: griglia, magnetismo,
evidenziazione dei campi, tema chiaro o scuro, compressione predefinita.

---

## Funzionalità

### Pagine

| Azione | Come |
| --- | --- |
| Inserire pagina vuota | *Pagine ▸ Inserisci pagina vuota…* |
| Inserire da un altro PDF | *Pagine ▸ Inserisci da file…* |
| Duplicare | *Pagine ▸ Duplica* |
| Estrarre in un nuovo documento | *Pagine ▸ Estrai in un nuovo documento…* |
| Dividere il documento | *File ▸ Dividi documento…* |
| Eliminare | *Pagine ▸ Elimina* |
| Ruotare | *Pagine ▸ Ruota a destra / a sinistra / di 180°* o `Ctrl+Shift+←/→` |
| Ruotare di 180° | *Pagine ▸ Ruota di 180°* |
| Dimensioni e orientamento | *Pagine ▸ Impostazione pagina…* |
| Ritagliare (bordi delle scansioni) | *Pagine ▸ Ritaglia pagina…* |
| Numerare le pagine | *Pagine ▸ Numerazione pagine…* |
| Riordinare | trascinando le miniature |

### Annotazioni

Evidenzia, sottolinea, barrato, onda, nota, timbro, forma (rettangolo, ellisse),
linea, freccia, gesso, poligono, casella di testo, immagine, collegamento,
redazione e firma.

Ogni annotazione si seleziona con un clic e si sposta trascinandola. Le
maniglie quadrate ne cambiano la dimensione; con la barra di stato si accorgono
subito se sono selezionate.

Le opzioni di aspetto (colore, spessore, riempimento, opacità) stanno in
*Annota ▸ Stile annotazione* e *Annota ▸ Stile evidenziazione*.

*Annota ▸ Appiattisci annotazioni* incide le annotazioni nel contenuto: dopo
questo non sono più modificabili, e il programma lo chiede prima di farlo.

### Moduli

I campi esistenti si compilano con un clic e si salvano nel documento. Con
l'evidenziazione dei campi attiva, ogni campo è circondato da un riquadro.

- *Strumenti ▸ Rileva campi e moduli* cerca i campi che esistono ma non sono
  dichiarati come tali;
- *Moduli ▸ Compila i campi* li imposta in una sequenza;
- *Annota ▸ Appiattisci campi* rende i campi testo non modificabile;
- *Annota ▸ Azzera campi* li riporta al valore iniziale.

**Per spostare o ridimensionare un campo** lo strumento *Seleziona* va
usato con **Alt+clic** sopra il campo: si apre l'editor solo con il clic
normale. Le maniglie ai lati cambiano la dimensione.

Con *Moduli ▸ Campo di testo* (e gli altri strumenti) si creano campi nuovi:
basta un clic sulla pagina, la dimensione predefinita è sensata e si può
correggere dopo.

### Firma

*Firma ▸ Inserisci firma…* (o `Ctrl+Shift+G`) apre il dialogo con quattro
schede: **Disegna**, **Tastiera**, **Immagine**, **Libreria**.

Le opzioni di inserimento sono sotto le schede: pagina, dimensione, opacità,
appiattimento su bianco e compilazione del campo firma se il modulo ne ha uno.

- **Libreria**: *Firma ▸ Libreria delle firme…* per salvare, rinominare e
  riusare le firme.
- *Firma ▸ Compila campo firma* apre la finestra di firma con il primo campo
  firma del modulo già selezionato.
- *Firma ▸ Firma digitale (certificato)…* firma con un certificato PKCS#12.

Il riquadro di disegno accetta la pressione dello stilo, se disponibile.

### Firma digitale

*Firma ▸ Firma digitale (certificato)…* firma il documento o un campo firma
esistente con un certificato `.p12`/`.pfx` protetto da password. Il documento
firmato non può più essere modificato.

*Moduli ▸ Verifica firma digitale* e *Strumenti ▸ Verifica firme…* controllano
le firme presenti, con esito, emittente e data.

### Ricerca e sostituzione

`Ctrl+F` apre il pannello di ricerca. I risultati si scorrono con i pulsanti o
con `F3` e `Maiusc+F3`, e la pagina si porta in vista da sola (nel campo di
ricerca anche con `Invio`).

*Sostituisci…* (`Ctrl+H`) sostituisce una parola o una frase, con possibilità di
distinguere maiuscole/minuscole e di limitare la ricerca alle pagine scelte.
Le stesse due opzioni valgono per la ricerca e per la sostituzione: con
*parola intera* una sostituzione non tocca «elazione» dentro «Relazione».
Anche le sostituzioni si annullano con `Ctrl+Z`.

La sostituzione riscrive la pagina: la parola viene coperta e la nuova scritta
al suo posto, con lo stesso corpo. L'ordine di lettura resta quello che si vede.

### Riconoscimento del testo (OCR)

*Strumenti ▸ OCR (riconosce testo)…* applica Tesseract alle immagini delle
pagine e aggiunge un livello di testo invisibile. Serve `tesseract` installato
con la lingua italiana.

### Sicurezza

*Strumenti ▸ Proteggi documento…* imposta password per aprire, per modificare
e i permessi (stampa, copia, modifica, annotazioni, estrazione).

Il programma non perde mai la cifratura in silenzio: se si salva un documento
protetto senza le password, il salvataggio viene rifiutato e lo si dice.

*Strumenti ▸ Verifica firme…* controlla le firme digitali.

### Esportazione e qualità

| Azione | Dove |
| --- | --- |
| Esporta (immagini PNG/JPEG/TIFF, testo, PDF/A) | *File ▸ Esporta…* |
| Stampa | `Ctrl+P` |
| Riduci dimensione | *File ▸ Riduci dimensione del file…* |
| PDF/A | *File ▸ Esporta…* → PDF/A |
| Unisci documenti | *File ▸ Unisci documenti…* |
| Trasforma le foto in un PDF | *File ▸ Converti immagini in PDF…* |

*File ▸ Converti immagini in PDF…* trasforma un mucchio di fotografie in un
documento: si scelgono le immagini, si mettono nell'ordine che si vuole, si
sceglie il formato della pagina, i margini e quante immagini ci stanno in ogni
pagina; il programma scrive un PDF nuovo e lo apre. Aprire una singola
immagine continua a fare la cosa ovvia: una pagina, della forma della foto.

*File ▸ Riduci dimensione del file…* ricomprime le immagini più grandi di una
certa soglia e riporta prima e dopo, così si vede se conviene.

Il pannello **Qualità** elenca i problemi tipici: font non incorporati,
immagini enormi, metadati, oggetti nascosti, annotazioni in cima al testo. Per
ogni problema c'è il pulsante per risolverlo.

### Allegati e commenti

*Annota ▸ Allega file…* allega un file al PDF. Il pannello **Allegati** li
elenca e li apre.

Il pannello **Commenti** elenca le annotazioni con testo: note, caselle di
testo e timbri.

### Segnalibri

Il pulsante **+** del pannello **Segnalibri** crea un segnalibro alla pagina
corrente. Si rinominano con un doppio clic, si riordinano con le frecce e si
eliminano dal pannello stesso.

---

## Scorciatoie da tastiera

L'elenco completo si vede in *? ▸ Scorciatoie da tastiera* (`F1`).

### File

| Tasto | Azione |
| --- | --- |
| `Ctrl+N` | Nuovo |
| `Ctrl+O` | Apri |
| `Ctrl+S` | Salva |
| `Ctrl+Shift+S` | Salva come |
| `Ctrl+P` | Stampa |
| `Ctrl+Q` | Esci |

### Modifica

| Tasto | Azione |
| --- | --- |
| `Ctrl+Z` | Annulla |
| `Ctrl+Y` | Ripeti |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` | Taglia, copia, incolla |
| `Ctrl+A` | Seleziona tutto |
| `Ctrl+F` | Trova |
| `Ctrl+H` | Sostituisci |
| `Ctrl+D` | Proprietà del documento |
| `Ctrl+,` | Preferenze |

### Visualizza

| Tasto | Azione |
| --- | --- |
| `Ctrl+0` | Adatta alla pagina |
| `Ctrl+1` | Adatta alla larghezza |
| `Ctrl+2` | Dimensione reale |
| `Ctrl++` / `Ctrl+-` | Ingrandisci, riduci |
| `Ctrl+Shift+P` | Pannello pagine |
| `Ctrl+Shift+L` | Pannelli laterali |
| `Ctrl+Shift+F` | Presentazione |
| `Ctrl+'` | Griglia |
| `F11` | Schermo intero |

### Pagine e strumenti

| Tasto | Azione |
| --- | --- |
| `Ctrl+Shift+←` / `→` | Ruota la pagina |
| `Ctrl+Shift+G` | Inserisci firma |
| `Ctrl+Shift+D` | Firma digitale |
| `Spazio` + trascina | Sposta la pagina |
| `F3` / `Maiusc+F3` | Risultato successivo, precedente |

---

## Dove finiscono i dati

Il programma non usa la rete e scrive solo in due cartelle dell'utente:

| Sistema | Configurazione | Dati |
| --- | --- | --- |
| Linux | `~/.config/korvaxoide-pdf-editor/` | `~/.local/share/korvaxoide-pdf-editor/` |
| Windows | `%APPDATA%\KorvaxoidePDF\` | `%APPDATA%\KorvaxoidePDF\` |
| macOS | `~/Library/Application Support/KorvaxoidePDF/` | idem |

Nella cartella dei dati ci sono le firme salvate, i font trovati sul sistema e
la copia di recupero.

Le firme salvate e i certificati **non** vengono mai inclusi nel PDF senza
chiedere: la firma digitale richiede un'azione esplicita.

---

## Programmi esterni opzionali

Korvaxoide PDF Editor funziona senza nulla di tutto questo; servono per funzioni
in più.

| Programma | Serve per | Senza |
| --- | --- | --- |
| `tesseract` | Riconoscimento del testo (OCR) | La voce è grigia |
| `ghostscript` (`gs`) | Esportazione PDF/A | La voce è grigia |

Su Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-ita ghostscript
```

Tesseract si può installare anche senza root, nella cartella dell'utente:
`run.sh` aggiunge `~/.local/bin` al `PATH`, quindi basta metterci l'eseguibile.

---

## Come è fatto il codice

```
pdfeditor/
  app.py              avvio, traduttore, impostazioni d'ambiente
  core/               il motore PDF, senza Qt
    document.py       pagine, annotazioni, campi, testo, sicurezza
    geometry.py       rettangoli, rotazioni, magnetismo
    history.py        annullamento e ripetizione
    settings.py       preferenze su disco
    textlayout.py     misura e impaginazione del testo
    units.py          formati pagina (A4, Letter, …)
  ui/                 l'interfaccia
    main_window.py    finestra, menu, toolbar, azioni
    page_view.py      vista a scorrimento, strumenti di disegno
    page_items.py     nodi di pagina, campi, selezione
    panels.py         pannelli laterali
    thumbnails.py     miniature delle pagine
    toolbars.py       barre e menu degli strumenti
    icons.py          icone disegnate a runtime, nessun file immagine
    theme.py          tema chiaro e scuro
    ocr.py            richiamo a tesseract
    printing.py       stampa, conversione PDF/A
    dialogs/          finestre e riquadri
  features/
    digitalsign.py    firma digitale PKCS#7
    quality.py        controlli di qualità e accessibilità
  signature/          tavolozza, tratti, rimozione sfondo, libreria
tests/                verifiche automatiche
tools/                generazione delle icone
```

Le regole seguite:

- **il motore non conosce l'interfaccia**: `core/` non importa nulla di `ui/`;
- **ogni modifica passa da `_mutate`**: così l'annullamento funziona e un'operazione
  fallita non lascia mezze modifiche;
- **le coordinate di scena sono in punti**: la scala la fa la trasformazione
  della vista, non il codice (mescolare le due produceva elementi fuori posto);
- **ogni azione dell'interfaccia è coperta da una verifica** che la esegue
  davvero, non che chiama il metodo.

---

## Verifiche

```bash
./venv/bin/python -m pytest tests/ -q     # 815 test
./venv/bin/python tests/integration.py    # 80 verifiche di integrazione
./venv/bin/python tests/finale.py         # 46 verifiche di collaudo
./venv/bin/python tests/visual.py         # catture dell'interfaccia
```

Le verifiche non si limitano a chiamare i metodi: `tests/test_interazione.py`
pilota la finestra con eventi Qt veri (clic, trascinamenti, tastiera) e
`tests/test_funzionalita.py` esercita ogni funzionalità una per una. È quello
che ha scoperto i difetti più gravi: menu che si svuotavano, riquadri dei campi
spostati, il riquadro di disegno della firma che non accettava tratti.

`tests/test_regressioni.py` e `tests/test_regressioni_ui.py` raccolgono i difetti
trovati esaminando l'editor voce per voce, ognuno con la spiegazione del
guasto: ogni forma e ogni spostamento su pagina ruotata, la firma che diventava
nera trascinata, la stampa che non partiva, il pannello dei commenti che non
rispondeva, i pulsanti di opzione che si spegnevano da soli.

---

## Documentazione ulteriore

| Documento | Contenuto |
| --- | --- |
| [`MANUALE.md`](MANUALE.md) | Guida completa, per argomento |
| [`SVILUPPO.md`](SVILUPPO.md) | Come si sviluppa e si rilascia |
| [`CHANGELOG.md`](CHANGELOG.md) | Cosa è cambiato da una versione all'altra |
| [`THIRD-PARTY.md`](THIRD-PARTY.md) | Licenze delle dipendenze |
| [`SECURITY.md`](SECURITY.md) | Come segnalare un difetto di sicurezza |

Questi documenti sono la traduzione di quelli nella radice del repository,
che sono in inglese e sono il testo di riferimento:
[`MANUAL.md`](../../MANUAL.md) ·
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) ·
[`CHANGELOG.md`](../../CHANGELOG.md) ·
[`THIRD-PARTY.md`](../../THIRD-PARTY.md) ·
[`SECURITY.md`](../../SECURITY.md)

---

## Licenza

AGPL-3.0-or-later. Il testo completo è in [`LICENSE`](../../LICENSE).

La licenza è imposta da **PyMuPDF**, che è AGPL: per chi preferisce la
licenza commerciale di Artifex basta acquistarla e sostituire la libreria.

L'AGPL è una copyleft, non una restrizione: vendere, distribuire e modificare
il programma sono tutti consentiti. L'unico obbligo è che **chi riceve il
programma riceva anche il sorgente** della stessa versione.

Qui l'obbligo è già soddisfatto: il codice di ogni versione pubblicata è
questo repository, e ogni rilascio su GitHub porta il tag corrispondente. Chi
scarica un binario trova il sorgente di quel file esatto con un clic su
*Source code* nella [pagina delle release](https://github.com/Korvaxoide/Korvaxoide-PDF-Editor/releases),
oppure con:

```bash
git clone https://github.com/Korvaxoide/Korvaxoide-PDF-Editor.git
git checkout v0.1.1
```

Korvaxoide PDF Editor non dà nessuna garanzia: è fornito «così com'è».
