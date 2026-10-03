"""Persistenza delle preferenze utente (JSON su disco)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def config_dir() -> Path:
    """Cartella di configurazione specifica della piattaforma."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "KorvaxoidePDF"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KorvaxoidePDF"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "korvaxoide-pdf-editor"


def data_dir() -> Path:
    """Cartella dati utente (firmate salvate, modelli, recupero)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "KorvaxoidePDF"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KorvaxoidePDF"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "korvaxoide-pdf-editor"


DEFAULTS: dict[str, Any] = {
    "recent_files": [],
    "max_recent": 12,
    "zoom_mode": "fit_width",
    "zoom": 1.0,
    "view_mode": "continuous",
    "view_rotation": 0,
    "unit": "pt",
    "grid_visible": False,
    "grid_size": 18.0,
    "snap_enabled": True,
    "snap_guides": True,
    "tool": "select",
    "autosave": True,
    "autosave_minutes": 10,
    "recover": True,
    "highlight_fields": True,
    "field_highlight_color": "#2f7fe0",
    "pdfjs_engine": "mupdf",
    "ocr_language": "ita",
    "ocr_dpi": 300,
    "signature_library": [],
    "default_pen_color": "#101828",
    "default_pen_width": 2.6,
    "default_typed_font": "",
    "last_export_dir": "",
    "print_dpi": 300,
    "compression_quality": 85,
    "max_image_megapixels": 40,
    "ui_language": "it",
    "confirm_destructive": True,
    "check_updates": False,
    "theme": "chiaro",
}


class Settings:
    """Preferenze persistenti con valori di default e salvataggio automatico."""

    def __init__(self, path: Path | None = None) -> None:
        self.dir = config_dir()
        self.path = path or (self.dir / "settings.json")
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in DEFAULTS:
                            self._data[k] = v
        except (OSError, ValueError):
            self._data = dict(DEFAULTS)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, values: dict[str, Any]) -> None:
        self._data.update(values)
        self.save()

    def reset(self) -> None:
        self._data = dict(DEFAULTS)
        self.save()

    def add_recent(self, file: str) -> None:
        # gli ingressi piu' vecchi di file gia' spariti non hanno senso: si
        # ripuliscono qui, altrimenti l'elenco si riempie di voci che non
        # aprono piu' nulla
        recent = [r for r in self.get("recent_files", []) if r != file and Path(r).exists()]
        recent.insert(0, file)
        self.set("recent_files", recent[: int(self.get("max_recent", 12))])

    def recent_files(self) -> list[str]:
        """File recenti ancora esistenti, ripulendo quelli spariti."""
        files = [r for r in self.get("recent_files", []) if Path(r).exists()]
        if len(files) != len(self.get("recent_files", [])):
            self.set("recent_files", files)
        return files

    def clear_recent(self) -> None:
        self.set("recent_files", [])

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
