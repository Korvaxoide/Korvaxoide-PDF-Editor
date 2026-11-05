"""Punto d'ingresso: ``python -m pdfeditor``."""

from .core import log

# Il log va preparato prima di importare ``app``: un guasto durante l'import
# dei moduli dell'interfaccia deve comunque lasciare una traccia.
log.setup()
log.install_excepthook()

from .app import main  # noqa: E402

main()
