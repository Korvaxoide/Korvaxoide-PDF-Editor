# Registro delle modifiche

> **Lingua:** Italiano · [English](../../CHANGELOG.md)

Le modifiche di Korvaxoide: PDF Editor. Il formato segue
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il versionamento è
[semantico](https://semver.org/lang/it/).

La versione vive in un punto solo, `__version__` in `pdfeditor/__init__.py`:
da lì la prendono il nome dell'AppImage, il nome dell'eseguibile Windows, la
versione del pacchetto macOS e la finestra *Informazioni sul programma*.

---

## 0.1.0 — 2026-10-03

Prima versione numerata. Prima di questa il numero era `1.0.0` di default e
non voleva dire niente, perché il programma non era mai stato pubblicato.

### Interfaccia

L'interfaccia parla italiano e inglese. La lingua segue quella del sistema e
si può cambiare quando si vuole da *Strumenti ▸ Lingua…* o dalle preferenze;
menu e barre cambiano subito, le finestre già aperte tengono la lingua con cui
sono state costruite. Il sorgente conserva le frasi in italiano: sono le chiavi
a cui è scritto il catalogo inglese, così una traduzione che manca mostra la
frase italiana invece di uno spazio vuoto.

### Aggiunto

- **Interfaccia in inglese**, selezionabile e memorizzata, quella del sistema
  quando non è stata scelta una lingua.
- **Firma**: disegno a mano libera con penna e opacità, firma digitata con
  font calligrafici, inserimento da immagine, rimozione dello sfondo
  (colore campionato, magic wand, soglia, spazzola), libreria delle firme con
  rinomina e riuso, inserimento in un campo firma esistente.
- **Firma digitale** PKCS#7 con certificato P12/PEM o autofirmato, e verifica.
- **Moduli**: lettura e scrittura dei campi AcroForm (testo, casella di
  spunta, pulsante di opzione, elenco, pulsante, firma), compilazione in
  linea, creazione di campi nuovi con proprietà, appiattimento e azzeramento.
- **Annotazioni**: evidenziazione, sottolineatura, barratura, ondulato,
  inchiostro libero, forme, nota, timbro, allegato, collegamento. Redazione
  permanente.
- **Pagine**: inserimento, duplicazione, eliminazione, estrazione, unione,
  divisione, riordino, rotazione, ritaglio, numerazione, impostazione pagina.
- **Ricerca e sostituzione** con maiuscole/minuscole, parola intera ed
  espressioni regolari, sui PDF anche scansionati grazie a OCR.
- **Sicurezza**: password di apertura, permessi, cifratura AES-256, rimozione
  protezione, controlli di qualità e accessibilità.
- **Esportazione** in PNG/JPEG/TIFF, testo, PDF/A (con Ghostscript) e stampa.
- **Firma visibile** in anteprima con possibilità di firmare il PDF aperto.
- **Annullamento e ripetizione** di ogni modifica.
- **Recupero**: copia periodica e proposta all'avvio dopo una chiusura
  improvvisa.
- **Tema chiaro e scuro**, propagato a pannelli e finestre.
- Avvio dalla sorgente su Linux e Windows (`./run.sh`, `run.bat`) ed eseguibile
  per entrambi i sistemi con PyInstaller (AppImage e `.exe`).
- Verifiche automatiche: 753 test, suite di integrazione e collaudo del
  flusso di lavoro, in esecuzione su Linux e Windows con Python 3.12 e 3.14.

### Corretto

Difetti trovati esercitando il programma voce per voce; la lista completa,
con la causa di ognuno, è nei messaggi di commit.

- Su una pagina ruotata ogni forma e ogni spostamento finivano nell'angolo
  opposto: la vista consegnava al motore coordinate dello schermo e il
  documento registrava coordinate di pagina.
- Il trascinamento attraversava le pagine e l'elemento si trovava sulla
  pagina sbagliata.
- Il clic nel corridoio fra due pagine selezionava con coordinate inventate.
- Dopo aver aperto un altro file restava una selezione fantasma: `Ctrl+C` e
  «Elimina» fallivano.
- Spuntare una casella di spunta riapriva il proprio editor e ripeteva la
  modifica all'infinito, facendo sparire la pagina dalla vista.
- Nel gruppo di pulsanti di opzione il padre copriva tutte le scelte e il
  clic su una le spegneva tutte; le opzioni potevano restare accese più di
  una insieme.
- Duplicare più pagine sceglieva quelle sbagliate e ne duplicava una due
  volte.
- Il testo selezionato non si poteva togliere con un clic.
- `Ctrl+S` non salvava, con o senza modifiche.
- L'esportazione perdeva titolo, autore, oggetto e parole chiave.
- La sostituzione del testo perdeva font, corpo e colore, cancellava le
  cornici delle tabelle e metteva il testo sotto tutto il resto della pagina.
- Il magnetismo agganciava solo in orizzontale.
- Le figure prive di testo alternativo non venivano mai segnalate.
- La stampa ignorava l'intervallo di pagine scelto e non aveva guardia sulla
  risoluzione né sull'errore della stampante.
- Le finestre di testo scartavano font, corpo, colore e allineamento
  scelti, a favore dello stile della barra.
- Il canale alfa si perdeva spostando o estraendo un'immagine, e una firma a
  paletta diventava nera.
- Dopo la rimozione della protezione ogni salvataggio successivo era
  rifiutato.

### Documentazione

- README presentativo con installazione per Ubuntu e Windows.
- MANUALE completo, per argomento.
- SVILUPPO con organizzazione del codice, regole e procedura di rilascio.
- THIRD-PARTY con le licenze di ogni dipendenza e il motivo della scelta
  AGPL.