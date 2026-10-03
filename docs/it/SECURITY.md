# Sicurezza

> **Lingua:** Italiano · [English](../../SECURITY.md)

## Come segnalare un difetto

**Non aprire una issue pubblica** per un difetto di sicurezza: chi la legge
può sfruttarlo prima che ci sia una correzione.

Scrivi un messaggio privato a
<https://github.com/Korvaxoide/Korvaxoide-PDF-Editor/security/advisories/new>
(oppure apri un advisory privato dalla pagina *Security* del repository).

Nella segnalazione servono:

- la versione del programma (si vede in *Informazioni sul programma*);
- il sistema operativo e la versione;
- che cosa succede aprendo il documento, e che cosa si vede;
- il documento di prova, se si può condividere in modo sicuro.

## Cosa ci si può aspettare

Risposta entro una settimana, una valutazione entro quindici giorni. Se il
difetto viene corretto, la correzione entra nella versione successiva e il
suo autore viene ringraziato nella pagina *Credits*, a meno che preferisca
l'anonimo.

## Il perimetro

Il programma **non usa la rete**: non apre connessioni, non invia nulla, non
telemetria. Un difetto che richieda di comunicare con l'esterno non riguarda
questo progetto.

I punti dove un documento entra nel programma e viene interpretato sono i
luoghi dove un difetto è plausibile: apertura di un PDF, eseguizione di
JavaScript incorporato, azioni di un collegamento, OCR con `tesseract`,
conversione PDF/A con Ghostscript, elaborazione di un allegato, verifica di
una firma digitale. Un difetto in queste zone è interessante anche se non
permette di prendere il controllo della macchina.

## Il modello di minaccia

- **Il documento è l'input ostile.** Un PDF può arrivare da qualunque fonte.
- **L'integrità della firma digitale è una promessa.** Un difetto che
  permette di dichiarare valida una firma che non lo è, o di firmare un
  contenuto diverso da quello mostrato, è grave per un utente che firma.
- **La cifratura non si perde in silenzio.** Il programma rifiuta di salvare
  quando non può conservare la protezione del documento, e lo dice. Un
  difetto in questa protezione è grave.
- **Le firme salvate sono materiale biometrico.** Una firma di una persona
  non deve poter essere esportata, copiata o mostrata a chi non dovrebbe
  vederla.

## Limiti noti

- Il programma non verifica la firma di chi pubblica i binari: su Windows un
  eseguibile non firmato fa scattare l'avviso di SmartScreen, e va scaricato
  dai rilasci di questo repository.
- Tesseract e Ghostscript sono programmi esterni, richiamati come
  subprocessi: hanno le loro vulnerabilità e la loro politica di
  aggiornamento. Installali dal tuo sistema.
- L'eliminazione del testo e la cifratura dipendono dal motore PDF
  (PyMuPDF/MuPDF): per lo stesso documento, due versioni diverse del motore
  possono dare un risultato diverso.