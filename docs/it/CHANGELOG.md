# Registro delle modifiche

> **Lingua:** Italiano · [English](../../CHANGELOG.md)

Le modifiche di Korvaxoide: PDF Editor. Il formato segue
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il versionamento è
[semantico](https://semver.org/lang/it/).

La versione vive in un punto solo, `__version__` in `pdfeditor/__init__.py`:
da lì la prendono il nome dell'AppImage, il nome dell'eseguibile Windows, la
versione del pacchetto macOS e la finestra *Informazioni sul programma*.

---

## Non pubblicato

### Corretti

- Su Windows il salvataggio non scriveva niente. MuPDF tiene aperto il file da
  cui ha aperto il documento, e Windows non permette di sostituire un file
  aperto: la sostituzione rispondeva sempre «Access is denied» e il
  contenuto nuovo non arrivava mai sul disco. Quando il file non si può
  sostituire il contenuto ci viene scritto dentro, dopo qualche tentativo: il
  file resta valido e le letture successive sono quelle del documento appena
  riscritto. Un file che un altro programma tiene bloccato viene ora
  dichiarato tale, invece di essere dato per salvato.

### Verifiche

- La suite girava solo su Linux: leggeva da `/tmp`, cercava i font sotto
  `/usr/share/fonts`, contava un Ghostscript assente come una funzione assente
  e costruiva un percorso impossibile con una cartella che non esiste. File
  temporanei, font e percorsi inutilizzabili vengono ora presi dagli
  aiutanti di `tests/ambiente.py`, su ogni piattaforma.
- Le macchine GitHub non installavano ciò che serve alla suite per partire:
  le librerie di piattaforma di Qt, per cui il Linux falliva all'import, e i
  font, per cui le verifiche della firma non avevano nulla su cui scrivere.
- Il controllo della licenza faceva fallire la build quando gnu.org non si
  raggiungeva. Un download fallito non dice niente del repository: ora viene
  ritentato e, se il testo non arriva, avvisa e lascia passare. A fermare la
  build è adesso solo un `LICENSE` cambiato.
- Cinquanta verifiche di interazione fallivano su Windows prima ancora di un
  clic: il PDF usato come modello veniva riscritto, nome compreso, mentre una
  finestra lo teneva aperto, e Windows non permette di riscriverlo. Ogni
  verifica costruisce adesso il proprio modello.
- La verifica del ritento quando un file è occupato per un momento saltava su
  Windows, dove la sostituzione non viene mai tentata: ora la prova apposta, e
  una seconda verifica copre il ritento della scrittura che Windows usa alla
  fine.
- Il timer che chiude i dialoghi di una verifica continuava a girare anche
  dopo che la verifica era finita, e chiudeva i dialoghi delle successive: una
  firma disegnata a mano spariva da sola.
- Una verifica misurava un trascinamento in punti PDF mentre il puntatore
  viaggia in pixel di schermo: dove un pixel vale qualche punto il campo era
  stato spostato correttamente e la verifica falliva lo stesso. Ora misura
  dove il puntatore è arrivato davvero.
- Un dialogo lasciato aperto poteva fermare tutta la suite, e una suite ferma
  teneva la macchina occupata finché la piattaforma si arrengeva dopo sei ore.
  Ora un dialogo che nessuno chiude viene chiuso dopo qualche secondo e ogni
  verifica ha un tempo massimo: una verifica bloccata fallisce in minuti e
  dice quale è stata.
- Taglia e Incolla su un elemento che non li accetta sollevavano un errore
  interno invece di dirlo: il messaggio era costruito con una parola diversa
  dal suo segnaposto. Ora ogni messaggio con un valore dentro viene confrontato
  con i suoi segnaposto.
- «Terze parti» apriva davvero il browser e su una macchina senza browser la
  chiamata non tornava mai: la verifica che preme ogni voce di menu registra
  l'indirizzo invece di aprirlo.

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