# Manuale di Korvaxoide PDF Editor

> **Lingua:** Italiano · [English](../../MANUAL.md)

Guida completa, per argomento. Per l'installazione vedi il
[README](../../README.md).

---

## Indice

1. [L'interfaccia](#linterfaccia)
2. [Documenti](#documenti)
3. [Pagine](#pagine)
4. [Visualizzazione](#visualizzazione)
5. [Selezionare e copiare](#selezionare-e-copiare)
6. [Annotazioni](#annotazioni)
7. [Moduli](#moduli)
8. [Firme](#firme)
9. [Firma digitale](#firma-digitale)
10. [Ricerca e sostituzione](#ricerca-e-sostituzione)
11. [Riconoscimento del testo](#riconoscimento-del-testo)
12. [Protezione](#protezione)
13. [Esportare e convertire](#esportare-e-convertire)
14. [Qualità del documento](#qualità-del-documento)
15. [Allegati e commenti](#allegati-e-commenti)
16. [Segnalibri](#segnalibri)
17. [Strumenti esterni](#strumenti-esterni)
18. [Problemi frequenti](#problemi-frequenti)

---

## L'interfaccia

```
┌──────────────────────────────────────────────────────────────┐
│ barra strumenti: apri, salva, stampa, cerca, strumenti, zoom  │
├────────────┬────────────────────────────────┬────────────────┤
│  Pagine    │        documento               │  pannello     │
│  ( miniature│        (la vista)             │  laterale:    │
│   scorrevoli)│                                │  ricerca,     │
│            │                                │  campi,       │
│            │                                │  segnalibri,  │
│            │                                │  commenti,    │
│            │                                │  allegati,    │
│            │                                │  strumenti     │
├────────────┴────────────────────────────────┴────────────────┤
│ barra di stato: pagina corrente, zoom, messaggi              │
└──────────────────────────────────────────────────────────────┘
```

**Il pannello laterale** ha una voce per ogni scheda. Si apre e si chiude con
*Visualizza ▸ Pannelli laterali* (`Ctrl+Shift+L`).

**La barra di stato** è la voce più utile mentre si lavora: dice sempre cosa è
appena successo, quale elemento è selezionato e che cosa si può fare con esso.

**Il pulsante di strumento** in alto a sinistra riporta lo strumento attivo.
`Esc` torna a *Seleziona*.

---

## Documenti

### Aprire

- doppio clic sul file, oppure *File ▸ Apri…* (`Ctrl+O`);
- *File ▸ Apri recente* per tornare agli ultimi aperti;
- trascinando il file sulla finestra.

Un documento protetto chiede la password per l'apertura. Se non si ricorda, si
può comunque aprire in sola lettura scegliendo l'apertura senza password.

### Salvare

- `Ctrl+S` salva sul posto;
- *File ▸ Salva come…* (`Ctrl+Shift+S`) sceglie un altro percorso;
- *File ▸ Salva una copia…* salva una copia e continua a lavorare sull'originale.

`Ctrl+S` si può premere anche senza aver cambiato nulla: il file viene
riscritto com'è. Serve a riacquistare i permessi di scrittura persi per
strada, o a rimettere a posto un file corretto a mano con un altro programma.

**Attenzione:** salvare un documento protetto senza le password viene
**rifiutato**, con un avviso. Il programma non produce mai un PDF senza
protezione in silenzio.

### Recupero

Se il programma si chiude in modo inatteso, alla riapertura propone la copia
di recupero salvata in `~/.local/share/korvaxoide-pdf-editor/`.

### Informazioni

*Modifica ▸ Proprietà del documento…* mostra titolo, autore, soggetto, parole chiave,
creatore del PDF, applicazione che l'ha prodotto, data di modifica e numero di
pagine. *XMP* apre i metadati avanzati.

---

## Pagine

### Ordinare

Le miniature a sinistra si trascinano. In alternativa:
*Pagine ▸ Duplica*, *Estrai in un nuovo documento…* e *Elimina*, che agiscono
sulle pagine selezionate; con `Maiusc` o `Ctrl` se ne selezionano più di una
contemporaneamente. *Pagine ▸ Seleziona tutte le pagine* (`Ctrl+Shift+A`)
seleziona l'intero documento.

### Ruotare

- *Pagine ▸ Ruota a destra / a sinistra / di 180°* ruota il contenuto;
- anche i pulsanti di rotazione nella barra in alto e le voci «Ruota a
  sinistra» / «Ruota a destra» del menu di contesta sulle miniature.

`Ctrl+Shift+freccia destra/sinistra` ruota la pagina corrente.

La rotazione riguarda il contenuto della pagina: gli strumenti di disegno, le firme
e i campi seguono la pagina come si vede, quindi si possono disegnare sopra
come su una pagina normale.

### Ritagliare

*Pagine ▸ Ritaglia pagina…* toglie i bordi bianchi o neri delle scansioni.
«Rileva il contenuto automaticamente» propone i margini; si possono correggere
a mano nei quattro campi.

Il ritaglio cambia la dimensione della pagina: il contenuto non viene
modificato né spostato, cambia solo l'area visibile.

### Numerare

*Pagine ▸ Numerazione pagine…* mette il numero in uno dei tre punti del piè di
 pagina (sinistra, centro, destra), con il formato che si vuole (`{n}` è il numero). Si può scegliere di
saltare la prima pagina e di mostrare anche il totale (`{n}/{tot}`).

La numerazione è un livello di testo: si vede a schermo e in stampa, si può
togliere con *Pagine ▸ Rimuovi numerazione*.

---

## Visualizzazione

### Zoom

| Modo | Tasto | Cosa fa |
| --- | --- | --- |
| Adatta alla pagina | `Ctrl+0` | l'intera pagina |
| Adatta alla larghezza | `Ctrl+1` | la larghezza della pagina |
| Dimensione reale | `Ctrl+2` | 100% |
| Ingrandisci | `Ctrl++` | del 25% |
| Riduci | `Ctrl+-` | del 25% |

La rotella del mouse scorre la pagina; `Ctrl` con la rotella cambia lo zoom.

Il pulsante in basso a destra mostra la percentuale.

### Modi di pagina

- **Continua**: le pagine una sotto l'altra, la più comune;
- **Pagina singola**: una pagina per volta, con navigazione;
- **Affiancate**: due pagine per schermo, come un libro.

*Visualizza ▸ Presentazione* (`Ctrl+Shift+F`) nasconde pannelli e barre e mostra
una pagina per volta a schermo intero. Si esce con lo stesso comando o con `Esc`.

### Strumenti di lettura

*Visualizza ▸ Griglia* mostra una griglia (Ctrl+'); *Magnetismo* fa agganciare
le annotazioni ai bordi e ai centri delle altre, ai bordi della pagina e alla
griglia, con le guide di riferimento disegnate mentre si trascina; *Evidenzia
campi* circonda i campi modulo.

*Visualizza ▸ Tema scuro* inverte i colori. Il tema scuro vale per tutto:
finestra, barre, pannelli laterali, miniature, finestre di dialogo e l'editor
aperto su un campo. La scelta viene ricordata fra un avvio e l'altro.

---

## Selezionare e copiare

Con lo strumento **Seleziona**:

- un clic e trascinamento su un'annotazione la seleziona e la sposta;
- un clic su un campo lo apre per la compilazione;
- **Alt+clic** su un campo lo seleziona invece di aprirlo, così si può spostare
  o ridimensionare;
- un trascinamento sul testo evidenzia le parole toccate;
- un clic in un punto qualsiasi toglie l'evidenziazione, anche fuori dalla pagina;
- le maniglie quadrate ridimensionano l'elemento selezionato;
- `Ctrl+A` seleziona tutto il testo della pagina, `Ctrl+C` copia.

Il testo copiato conserva il formato: incollando in un editor di testo resta
semplice, incollando in un foglio di calcolo o in Word mantiene la tabella.

---

## Annotazioni

### Gli strumenti

**Evidenziatori**: evidenzia, sottolinea, barrato, onda. Si trascinano sopra il
testo: l'altezza si adatta da sola alla riga.

**Forme**: rettangolo, ellisse, linea, freccia, poligono, gesso (disegno a mano
libero). Si disegnano trascinando.

**Testo e immagine**: casella di testo (si apre un editor con font, corpo,
allineamento, colore, bordo, riempimento) e immagine (da file o dagli
appunti).

**Testo libero** (`Annota ▸ Testo libero`) è un'annotazione, non una casella di
testo: si sposta, si riapre, si cancella e compare nel pannello dei commenti,
mentre la casella di testo viene incisa nel contenuto della pagina. Grassetto,
corsivo e sottolineatura si scelgono nella finestra che si apre o con le leve
**B**, **I** e **U** della barra del testo.

**Nota**: un post-it con un'icona a scelta.

**Timbro**: un timbro testuale nelle forme previste.

**Collegamento**: si traccia un riquadro e si scrive l'indirizzo.

**Redazione**: copre in modo distruttivo il testo scelto, che sparisce dal
file. Si trascina un rettangolo sulle parole da cancellare; il programma chiede
conferma, perché l'operazione è permanente e non si annulla con il rettangolo.

**Allega file**: allega qualsiasi file al PDF.

### Modificare un'annotazione

Un clic la seleziona, le maniglie ne cambiano la dimensione, il trascinamento la
sposta. Il menu contestuale offre proprietà, copia, elimina.

Se sotto il cursore c'è sia un'annotazione sia un collegamento, vince
l'annotazione: il collegamento si apre solo dove non c'è nient'altro da
prendere. Con gli strumenti di disegno il clic apre il collegamento solo con
lo strumento di selezione attivo, così si può disegnare sopra un link.

*Annota ▸ Appiattisci annotazioni* le incide nel contenuto della pagina: da quel
momento non sono più modificabili. È la via per mandare a qualcuno un PDF che
non possa più essere alterato.

**Le proprietà dell'immagine**: con lo strumento Immagine selezionato,
*Proprietà immagine* apre una finestra con larghezza e altezza in punti,
l'opzione per mantenere le proporzioni e quella per ritagliare la parte che
esce dalla pagina. Vale per ogni immagine già presente, non solo per quelle
appena inserite.

### Colori e stili

*Annota ▸ Stile annotazione* sceglie colore, spessore, riempimento e opacità
per le forme. *Annota ▸ Stile evidenziazione* per gli evidenziatori. Le scelte
valgono per le annotazioni successive.

---

## Moduli

### Compilare

Con l'evidenziazione attiva, ogni campo è circondato da un riquadro azzurro.
Un clic dentro il campo apre l'editor al posto giusto e scrive nel documento
mentre si digita.

I campi con un menu a tendina si scelgono, le caselle di spunta si spuntano, i
pulsanti di opzione si selezionano.

`Tab` passa al campo successivo.

### Campi nuovi

*Moduli ▸ Campo di testo* (e casella di spunta, pulsante di opzione, menu a
tendina, pulsante) mette lo strumento in mano: un clic sulla pagina crea il
campo con una dimensione predefinita. Si può trascinare per scegliere le
misure.

Le proprietà si aprono con un doppio clic sul campo: nome, valore, font, corpo,
colore, opacità, suggerimento, obbligatorietà, sola lettura, lunghezza massima.

### Campi esistenti ma non dichiarati

*Strumenti ▸ Rileva campi e moduli* trasforma in campi veri le caselle vuote che
un produttore ha disegnato a mano: si possono così compilare e salvare.

### Compilare in sequenza

*Moduli ▸ Compila tutti i campi vuoti* apre i campi uno dopo l'altro, utile per un modulo
lungo.

### Azzerare e appiattire

*Annota ▸ Azzera campi* riporta tutto al valore iniziale.
*Annota ▸ Appiattisci campi* trasforma i campi in testo fisso: il modulo non è
più compilabile, il testo resta.

---

## Firme

### Creare una firma

*Firma ▸ Inserisci firma…* o `Ctrl+Shift+G`, oppure lo strumento Firma: un clic
sulla pagina apre il dialogo con la firma già posizionata dove si è cliccati.

Il dialogo ha quattro schede.

**Disegna** — si firma col mouse o col dito. Se si usa uno stilo, la pressione
modifica lo spessore del tratto.

**Tastiera** — si scrive il nome e si sceglie tra i font trovati sul sistema,
con colore, corpo e inclinazione.

**Immagine** — si carica un file o si incolla dagli appunti. C'è anche la
rimozione automatica dello sfondo, con pennello, tolleranza, soglia e sfocatura
del bordo, per staccare la firma da una carta fotografata.

**Libreria** — le firme già salvate, con rinomina e eliminazione.

### Le opzioni di inserimento

Sotto le schede:

- **Pagina**: in quale pagina metterla;
- **Dimensione**: larghezza e altezza in punti;
- **Opacità**: da 10% a 100%;
- **Appiattisci su bianco**: la firma viene incidata nel contenuto invece di
  restare sopra;
- **Campo firma**: se il documento ne ha uno, la firma viene scritta dentro il
  suo riquadro e il campo ne assume il valore.

### Libreria

*Firma ▸ Libreria delle firme…* salva la firma con un nome e la rende
riutilizzabile. *Firma ▸ Tutte le firme salvate* le elenca nel menu e le
inserisce con un clic.

Le firme salvate stanno in `~/.local/share/korvaxoide-pdf-editor/firme/`.

---

## Firma digitale

*Firma ▸ Firma digitale (certificato)…*.

Serve un certificato in formato PKCS#12 (`.p12` o `.pfx`). Si sceglie il file,
si scrive la password, e si firma:

- l'intero documento, oppure
- un campo firma, se il modulo ne ha uno.

Il risultato è una firma valida: il documento non può più essere modificato senza
invalidarla.

**Verificare:** *Moduli ▸ Verifica firma digitale* mostra esito, firmatario,
emittente e data di ogni firma trovata. *Strumenti ▸ Verifica firme…* fa la
stessa cosa sull'intero documento.

---

## Ricerca e sostituzione

### Cercare

`Ctrl+F`. Si scrive nella casella e si preme `Invio` per il risultato successivo,
`Maiusc+F3` per il precedente. La pagina si porta in vista da sola e la
posizione è evidenziata.

Opzioni: distinguere maiuscole e minuscole e parole intere (che esclude
«ore» dentro «Lorem»). La ricerca prende il testo alla lettera: `(` cerca una
parentesi, non un'espressione regolare.

### Sostituire

`Ctrl+H` apre la sostituzione. Si indica cosa cercare e cosa mettere al suo
posto, e si sceglie fra sostituzione singola, successiva, precedente e tutte.

La sostituzione **riscrive la pagina**: la parola trovata viene coperta e la
nuova scritta al suo posto, con lo stesso corpo e la stessa posizione. Il testo
non viene spostato e l'ordine di lettura resta quello che si vede.

Le sostituzioni si annullano con `Ctrl+Z` come qualsiasi altra modifica.

## Riconoscimento del testo

*Strumenti ▸ OCR (riconosce testo)…*.

Serve `tesseract` con la lingua italiana (`tesseract-ocr-ita`).

Il riconoscimento aggiunge alle pagine un livello di testo invisibile: il testo
diventa selezionabile e ricercabile, ma l'aspetto non cambia.

Va bene per le scansioni e per le fotografie di documenti stampati.

---

## Protezione

*Strumenti ▸ Proteggi documento…*

Si possono impostare:

- **password per aprire**: serve per leggere il documento;
- **password per modificare**: si apre in sola lettura senza di essa;
- **permessi**: stampa, copia, modifica, annotazioni, modifica dei moduli,
  estrazione di pagine e di immagini.

La protezione si applica a una **copia** del documento, chiamata
`nome_protetto.pdf` accanto all'originale, che resta come era.

*Rimuovi protezione* toglie la cifratura: chiede la password del proprietario.

Il programma non perde mai la cifratura in silenzio: se si salva un documento
protetto senza le password, il salvataggio viene rifiutato e lo si dice.

---

## Esportare e convertire

### File ▸ Esporta…

Si sceglie cosa ottenere:

- **PDF**: un'altra copia, eventualmente solo alcune pagine o con protezione;
- **Immagini**: PNG o JPEG, una per pagina, con la risoluzione desiderata;
- **Testo**: il testo di tutto il documento o di una pagina;
- **HTML**: per mettere il documento sul web.

### File ▸ Importa da immagini…

Trasforma un insieme di immagini (JPEG, PNG, TIFF, BMP, WebP) in un PDF,
nell'ordine in cui vengono selezionate.

### File ▸ Unisci documenti…

Accorcia più PDF in uno, nell'ordine scelto, con la possibilità di inserire
alcune pagine di ogni documento.

### File ▸ Dividi documento…

Divide il PDF in parti, scegliendo dove: a ogni N pagine, in un numero fissato di
parti, in un punto preciso o per estrazione di un intervallo.

### Stampa

`Ctrl+P`. Si sceglie la stampante, l'intervallo di pagine, il numero di copie e
l'orientamento.

### PDF/A

Dentro *File ▸ Esporta…*, scegliendo il formato PDF e il livello PDF/A. Serve
`ghostscript`; al termine il programma verifica il risultato e dice se la
conversione è riuscita.

---

## Qualità del documento

### Il pannello Qualità

La scheda **Qualità** del pannello laterale esamina il file e segnala:

- font non incorporati (il testo può apparire diverso altrove);
- immagini molto grandi (che appesantiscono il file);
- metadati che dicono più di quanto serve (autore, programma che ha creato il
  file);
- annotazioni e campi ancora modificabili;
- oggetti nascosti;
- collegamenti esterni.

Ogni voce dice che cosa fare e, dove possibile, il pulsante per risolverla.

### Riduci dimensione

*File ▸ Riduci dimensione del file…*

Il programma elenca le immagini con la loro dimensione e il loro peso, e fa
vedere quanto si guadagnerebbe. Si sceglie la qualità e la risoluzione massima.

Prima e dopo compaiono affiancate, con il risparmio in percentuale.

---

## Allegati e commenti

**Allegati** — *Annota ▸ Allega file…* allega un file al PDF. Il pannello
**Allegati** li elenca, permette di aprirli e di rimuoverli.

**Commenti** — il pannello elenca le annotazioni che hanno testo: note, caselle
di testo, timbri. Si può cercare fra i commenti, filtrarli per tipo e
raggiungere quello che interessa sulla pagina.

---

## Segnalibri

Il pulsante **+** del pannello **Segnalibri** (o doppio clic sul segnalibro
stesso) crea un segnalibro alla pagina corrente, con il nome che si vuole.

Nel pannello si possono:

- rinominare (doppio clic sul nome);
- spostare in su e in giù per riordinarli;
- raggruppare con i livelli;
- eliminare;
- saltare a una pagina con un clic.

---

## Strumenti esterni

| Programma | Per che cosa | Se manca |
| --- | --- | --- |
| `tesseract` | OCR | la voce è grigia e spiega perché |
| `ghostscript` (`gs`) | PDF/A | la voce è grigia e spiega perché |

Su Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-ita ghostscript
```

Su Fedora: `sudo dnf install tesseract tesseract-langpack-ita ghostscript`

Tesseract si può installare anche senza diritti di amministratore, nella
cartella dell'utente: `run.sh` aggiunge `~/.local/bin` al `PATH`, quindi è
sufficiente copiarci l'eseguibile.

---

## Problemi frequenti

**«Non vedo le opzioni del dialogo»**
Tutti i dialogi si adattano allo schermo e il contenuto scorre. Se resta
poco, riduci la dimensione della finestra principale.

**«Un campo sembra fuori posto»**
La vista mostra la pagina in scala: l'evidenziazione dei campi aiuta a
vedere dove sono. Se un campo sembra spostato, salva e riapri il documento.

**«Non riesco a spostare un campo»**
Serve **Alt+clic**: il clic normale apre l'editor per scriverci dentro.

**«La firma è sparita o è nel posto sbagliato»**
La firma è un oggetto come gli altri: con lo strumento *Seleziona* si clicca e
si trascina. Se non la vedi, guarda *Visualizza ▸ Presentazione*: la firma viene
messa al centro di ciò che è a schermo, quindi si vede subito.

**«La firma scritta a tastiera è una fila di quadratini»**
Il font scelto non contiene le lettere. Nella lista i font che le hanno sono
in cima; quelli che non le hanno sono in fondo e lo dicono.

**«Il tema scuro non è completo»**
Se un dialogo aperto prima del cambio resta chiaro, chiudilo e riaprilo: i
dialogi prendono il tema attivo quando vengono creati.

**«Il pulsante non c'è più»**
*Visualizza ▸ Pannelli laterali* (`Ctrl+Shift+L`) e *Pannello pagine*
(`Ctrl+Shift+P`).

**«Ho perso il lavoro»**
*File ▸ Recupera* (o l'avviso all'avvio). Il programma salva una copia di
recupero a ogni modifica.

**«Non posso salvare un documento protetto»**
È il comportamento voluto: salvare un PDF protetto senza le password produrrebbe
un file senza protezione. Usa *File ▸ Salva una copia…* e poi *Strumenti ▸
Proteggi documento…*.

**«La firma non si inserisce»**
Controlla che nella scheda scelta ci sia qualcosa: un trucco disegnato, un nome
scritto, un'immagine caricata o una firma della libreria. Senza contenuto il
pulsante *Inserisci* non fa nulla e lo dice.

**«Il PDF/A non si produce»**
Serve Ghostscript, che va installato a parte. Si trova in *File ▸ Esporta…*,
scegliendo «PDF/A (archiviazione)» come formato e il livello PDF/A: non è una
voce di menu a sé.
