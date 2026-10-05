# Registro delle modifiche

> **Lingua:** Italiano · [English](../../CHANGELOG.md)

Le modifiche di Korvaxoide PDF Editor. Il formato segue
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il versionamento è
[semantico](https://semver.org/lang/it/).

La versione vive in un punto solo, `__version__` in `pdfeditor/__init__.py`:
da lì la prendono il nome dell'AppImage, il nome dell'eseguibile Windows, la
versione del pacchetto macOS e la finestra *Informazioni sul programma*.

---

## Non pubblicato

### Cambiato

- **Il programma parte sensibilmente più in fretta.** Misurato con
  `tools/bench_startup.py` sulla macchina di riferimento, il tempo dal primo
  atto del processo alla prima finestra dipinta scende di circa il 27% (da
  circa 340 ms a circa 250 ms), misurato su otto coppie alternate di esecuzioni.
  Il guadagno sta in ciò che il programma carica
  prima di potersi mostrare:
  - **NumPy non si carica più all'avvio.** Da solo costa circa 70 ms ed entrava
    da `signature.bgremove`, la rimozione dello sfondo di un'immagine di firma.
    All'avvio quel modulo non lo tocca nessuno, ma `signature.manager` lo
    importava per poter salvare un PNG. I moduli delle firme che servono solo
    alla libreria delle firme salvate sono ora importati dai metaggi che li
    usano.
  - **Pillow non si carica più all'avvio.** Serviva solo per leggere e scrivere
    le immagini delle firme.
  - **Quasi duemila righe di finestre di dialogo non si importano più
    all'avvio.** `dialogs/props.py` (circa 8 ms) e `signature_dialog.py`
    (circa 5 ms) vengono importati dalle azioni che li aprono, come già
    facevano `printing`, `ocr` e `thumbnails`.
  - **Il catalogo inglese non si legge più all'import.** Il modulo finiva
    applicando la lingua predefinita, e quindi leggeva e interpretava 36 KiB di
    JSON prima che l'avvio potesse leggere la preferenza della lingua; a un
    utente italiano quel lavoro finiva scartato, perché l'italiano è la lingua
    del sorgente e non ha catalogo.
  - **L'icona dell'applicazione viene disegnata una volta sola invece che a ogni
    richiesta.** Il desktop la chiede più di una volta, per il riquadro, per il
    menu e per le anteprime, e ogni volta erano 256×256 pixel da ridisegnare.

- **Recuperare un documento non salvato non chiede più prima che la finestra
  sia comparsa.** La domanda veniva posta dal costruttore, e una finestra
  modale blocca: la domanda compariva *prima* della finestra del programma, e
  si leggeva come un avvio lento. Ora arriva al primo giro del ciclo di eventi,
  sopra una finestra già a schermo. Aprire un documento — dal menu o dalla riga
  di comando — ha comunque la precedenza: il recupero non viene proposto al suo
  posto.

- **L'elenco dei font disponibili si fa una volta per sessione.** Enumerare i
  font del sistema apre ognuno con MuPDF per vedere se ha le lettere latine:
  sono circa 100 ms su una macchina con il set di font solito. La finestra
  della firma chiedeva l'elenco due volte (l'elenco stesso e il font
  predefinito, che lo richiede) e ogni firma digitata senza un percorso valido
  lo chiedeva di nuovo. `typed.svuota_cache_font()` li rivede dopo aver
  installato un font a programma aperto.

### Corretto

- **Il file delle preferenze veniva riscritto durante l'avvio.** Leggere i file
  recenti — che avviene mentre i menu si costruiscono — controllava ogni voce e,
  se qualcuna era stata cancellata nel frattempo, riscriveva tutto il JSON su
  disco prima che la finestra comparisse. Ora la pulizia resta in memoria e
  viene salvata con il salvataggio successivo, che avviene comunque alla
  chiusura.

- **Un'impostazione di MuPDF che non poteva mai entrare in vigore.** All'avvio
  si chiedeva un limite di 200 MiB per il deposito interno con
  `TOOLS.store_size(...)`. In PyMuPDF 1.28 sia `store_size` sia `store_maxsize`
  sono getter che restituiscono `None` e non hanno un setter, quindi quel
  limite non era solo non applicato, era proprio inexpressibile. La chiamata
  sollevava `TypeError`, che l'`except` intorno accettava in silenzio, e la riga
  sembrava funzionare.

- **`QT_ENABLE_HIGHDPI_SCALING` e `QT_AUTO_SCREEN_SCALE_FACTOR` erano
  impostate per Qt 5.** Entrambe non fanno niente da Qt 6, dove lo schermo ad
  alta risoluzione è attivo di serie. Erano rimaste nel codice e facevano
  credere che toglierle avrebbe sfocato l'interfaccia.

- **`SignatureLibrary` creava la sua cartella tre volte per operazione.** Il
  percorso dell'indice veniva ricalcolato a ogni `load` e `save` confrontando la
  cartella con `library_dir()`, e ogni confronto creava la directory.

### Aggiunto

- `tools/bench_startup.py`, che stampa l'avvio fase per fase e dice quali
  librerie di terze parti si porta dietro. Il costo dell'avvio era un'opinione
  finché non c'è stato un modo per misurarlo, e un costo così non si vede in
  revisione: nessuno guarda un `import` in più in cima a un file e pensa che
  qualcosa sia diventato più lento.

- `tests/test_avvio.py`, che in un interprete pulito verifica che la finestra
  non si porti dietro NumPy, Pillow o le finestre di dialogo, e che i dialoghi
  si aprano ugualmente con l'import pigro. Undici dei suoi controlli falliscono
  sulla versione precedente: senza di essi, qualunque di questi costi può
  tornare un import alla volta, senza che nessuno se ne accorga.

## 0.1.1 — 2026-10-04

Correzione alla compilazione. Il programma in sé non cambia: questa versione
esiste perché il tag punti a un sistema di compilazione che riesca davvero a
produrre l'eseguibile Windows.

### Corretto

- **L'eseguibile Windows non si poteva compilare in file singolo.** La
  specifica PyInstaller passava `exclude_binaries=True` a `EXE()` e poi eseguiva
  `COLLECT` senza condizioni, quindi poteva produrre solo una cartella, e
  PyInstaller rifiutava il parametro con `option(s) not allowed:
  --onedir/--onefile`. `build_windows.ps1` cercava `dist\KorvaxoidePDF.exe`, non
  lo trovava e finiva con l'avviso "eseguibile non trovato" senza creare la
  copia con la versione.
- **Potatura Qt nel file singolo.** Con la cartella i moduli Qt inutili venivano
  cancellati da disco dopo `COLLECT`; nel file singolo vengono tolti dalla lista
  che finisce dentro l'eseguibile, prima di `EXE`, e solo sotto `PySide6/Qt`,
  così l'interprete, le estensioni Python, PyMuPDF e la cifratura restano
  tutti.

### Cambiato

- **La struttura si sceglie per piattaforma**: file singolo su Windows, cartella
  su Linux e macOS. Linux ha bisogno della cartella perché `build_linux.sh`
  impacchetta `dist/NOME/` in un AppImage, e su macOS `BUNDLE` richiede la
  raccolta. `KorvaxoidePDF_ONEDIR=1` o `=0` forza la scelta.

### Distribuzione

- L'eseguibile Windows non è firmato. Su Windows 11 con Smart App Control
  attivo, Windows può mostrare un avviso prima di avviarlo.
- L'AppImage allegato a questa versione è la build 0.1.0, invariata: non è
  stato ricostruito per la 0.1.1.

## 0.1.0 — 2026-10-04

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
- Verifiche automatiche: 769 test, suite di integrazione e collaudo del
  flusso di lavoro, in esecuzione su Linux e Windows con Python 3.12 e 3.14.

### Cambiato

- Il programma ora si chiama Korvaxoide PDF Editor ovunque si nomini: il titolo
  della finestra, la finestra *Informazioni sul programma*, la voce di menu, il
  pacchetto macOS, il produttore scritto in ogni PDF esportato e la
  documentazione. Il due punti del vecchio «Korvaxoide: PDF Editor» è sparito.
  L'indirizzo del repository, i nomi dei file e le cartelle di configurazione
  restano come sono: appartengono all'installazione e non al nome sulla
  etichetta, e rinominarli lascerebbe senza posto le impostazioni di chi usa
  già il programma.

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
- `Ctrl+S` non salvava, con o senza modificazioni.
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
- Su Windows il salvataggio non scriveva niente. MuPDF tiene aperto il file da
  cui ha aperto il documento, e Windows non permette di sostituire un file
  aperto: la sostituzione rispondeva sempre «Access is denied» e il
  contenuto nuovo non arrivava mai sul disco. Quando il file non si può
  sostituire il contenuto ci viene scritto dentro, dopo qualche tentativo: il
  file resta valido e le letture successive sono quelle del documento appena
  riscritto. Un file che un altro programma tiene bloccato viene ora
  dichiarato tale, invece di essere dato per salvato.

La distribuzione era rotta anch'essa, e un rilascio è esattamente il posto in
cui si vede.

- La compilazione Linux non arrivava mai all'AppImage. La cartella che
  assemblava aveva un percorso relativo e `appimagetool` veniva chiamato da
  dentro `dist/`, quindi cercava `dist/dist/…`, non trovava niente e la
  compilazione si fermava con un errore che non dice la causa. Il percorso è
  ora assoluto.
- L'AppImage non partiva neppure quando la cartella veniva messa insieme a
  mano: dentro non c'era `AppRun`, il runtime montava l'immagine, non trovava
  nulla da eseguire e usciva con «Failed to run AppRun». `build_linux.sh` ora
  scrive l'`AppRun` che avvia il programma.
- La voce di menu e l'AppImage non avevano icona. Il file veniva installato con
  il nome del programma mentre la voce di menu chiede
  `korvaxoide-pdf-editor`, la ricerca non trovava niente e la voce restava con
  il simbolo generico.

### Documentazione

- README presentativo con installazione per Ubuntu e Windows.
- MANUALE completo, per argomento.
- SVILUPPO con organizzazione del codice, regole e procedura di rilascio.
- THIRD-PARTY con le licenze di ogni dipendenza e il motivo della scelta
  AGPL.

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