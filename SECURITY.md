# Security

> **Language:** English · [Italiano](docs/it/SECURITY.md)

## How to report a defect

**Do not open a public issue** for a security defect: whoever reads it may use
it before a fix exists.

Send a private message at
<https://github.com/Korvaxoide/Korvaxoide-PDF-Editor/security/advisories/new>
(or open a private advisory from the repository's *Security* page).

A report needs:

- the program version (shown in *Informazioni sul programma* / About);
- the operating system and its version;
- what happens when the document is opened, and what you see;
- a test document, if it can be shared safely.

## What to expect

An acknowledgement within a week, an assessment within two weeks. If the defect
is fixed, the fix lands in the next release and its author is credited on the
*Credits* page, unless they prefer to stay anonymous.

## Scope

The program **does not use the network**: it opens no connection, sends nothing,
has no telemetry. A defect that requires talking to something outside the
machine is not in scope here.

The places where a document enters the program and gets interpreted are where
a defect is plausible: opening a PDF, running embedded JavaScript, following a
link, OCR with `tesseract`, PDF/A conversion with Ghostscript, processing an
attachment, verifying a digital signature. A defect in those areas is
interesting even if it does not grant control of the machine.

## Threat model

- **The document is untrusted input.** A PDF can arrive from any source.
- **Integrity of a digital signature is a promise.** A defect that lets the
  program call a signature valid when it is not, or sign content different from
  what is displayed, is serious for anyone who signs.
- **Encryption is never lost quietly.** The program refuses to save when it
  cannot preserve a document's protection, and says so. A defect in that
  protection is serious.
- **Saved signatures are biometric material.** Someone's signature must not be
  exportable, copyable or visible to those who should not see it.

## Known limits

- The program does not verify the signature of whoever publishes the binaries:
  on Windows an unsigned executable triggers the SmartScreen warning, so get it
  from this repository's releases.
- Tesseract and Ghostscript are external programs, invoked as subprocesses:
  they have their own vulnerabilities and their own update policy. Install them
  from your system.
- Text removal and encryption depend on the PDF engine (PyMuPDF/MuPDF): for the
  same document, two different versions of the engine can give a different
  result.