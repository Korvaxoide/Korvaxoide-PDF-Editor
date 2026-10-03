"""Tema visivo: colori, spaziature e foglio di stile Qt."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Palette:
    """Colori dell'interfaccia."""

    bg: str = "#f2f3f5"
    surface: str = "#ffffff"
    surface_alt: str = "#f7f8fa"
    panel: str = "#ffffff"
    border: str = "#d8dbe1"
    border_strong: str = "#b9bec8"
    text: str = "#1b1f27"
    text_dim: str = "#5b6472"
    text_disabled: str = "#9aa2b1"
    accent: str = "#2f6fdb"
    accent_hover: str = "#2560c4"
    accent_soft: str = "#dce8fb"
    danger: str = "#c8362f"
    warn: str = "#c98a12"
    ok: str = "#2e8b57"
    selection: str = "#2f6fdb"
    page_shadow: str = "#00000022"
    grid: str = "#9aa2b1"
    annot: str = "#7a4fd6"
    field_bg: str = "#eef4ff"
    field_border: str = "#2f6fdb"
    signature: str = "#0f766e"
    #: le maniglie di ridimensionamento stanno nella palette e non nelle
    #: misure: con i colori fissi sul tema chiario restavano bianche con bordo
    #: blu anche a tema scuro, e non si vedevano
    handle_fill: str = "#ffffff"
    handle_border: str = "#2f6fdb"

    def qcolor(self, key: str):
        from PySide6.QtGui import QColor

        return QColor(getattr(self, key, "#000000"))


LIGHT = Palette()

DARK = Palette(
    bg="#22262e",
    surface="#2b303a",
    surface_alt="#313742",
    panel="#2b303a",
    border="#3d4450",
    border_strong="#525b6b",
    text="#e8eaee",
    text_dim="#a7b0bf",
    text_disabled="#6c7686",
    accent="#5b93f0",
    accent_hover="#6fa1f5",
    accent_soft="#2c3f5e",
    danger="#e06a63",
    warn="#e0b04a",
    ok="#5fbf8b",
    selection="#5b93f0",
    page_shadow="#00000066",
    grid="#6c7686",
    annot="#a98ce8",
    field_bg="#2b3a52",
    field_border="#5b93f0",
    signature="#3fb8a8",
    handle_fill="#e8eaee",
    handle_border="#5b93f0",
)


@dataclass
class Metrics:
    """Spaziature e dimensioni."""

    radius: int = 6
    pad: int = 8
    gap: int = 6
    toolbar_h: int = 34
    sidebar_w: int = 268
    handle: int = 8
    page_gap: int = 22
    thumb_w: int = 132
    font_size: int = 10
    field_font_size: int = 9
    snap_tol: float = 5.0


METRICS = Metrics()

#: palette attualmente in uso. Le finestre e i pannelli la leggono quando si
#: costruiscono, così seguono il tema scuro senza essere informati uno a uno:
#: prima ogni dialogo partiva da LIGHT e il tema scuro lo lasciava chiaro.
_attiva: Palette = LIGHT


def attiva(pal: "Palette") -> "Palette":
    """Imposta la palette in uso e la restituisce."""
    global _attiva
    _attiva = pal
    return _attiva


def corrente() -> Palette:
    """Palette attualmente in uso."""
    return _attiva


def stylesheet(p: Palette, m: Metrics = METRICS) -> str:
    """Foglio di stile Qt derivato dalla tavolozza."""
    return f"""
QWidget {{
    background: {p.bg};
    color: {p.text};
    font-size: {m.font_size}pt;
}}
QMainWindow, QDialog {{ background: {p.bg}; }}
QToolBar {{
    background: {p.surface};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 3px 6px;
    spacing: 3px;
}}
QToolBar QToolButton {{
    padding: 5px 8px;
    border-radius: {m.radius}px;
    border: 1px solid transparent;
    color: {p.text};
}}
QToolBar QToolButton:hover {{ background: {p.surface_alt}; border-color: {p.border}; }}
QToolBar QToolButton:checked {{
    background: {p.accent_soft};
    border-color: {p.accent};
    color: {p.accent};
}}
QToolBar QToolButton:disabled {{ color: {p.text_disabled}; }}
QToolBar::separator {{
    background: {p.border};
    width: 1px;
    margin: 4px 5px;
}}
QStatusBar {{
    background: {p.surface};
    border-top: 1px solid {p.border};
    color: {p.text_dim};
}}
QStatusBar QLabel {{ padding: 0 6px; }}
QMenuBar {{ background: {p.surface}; border-bottom: 1px solid {p.border}; }}
QMenuBar::item:selected {{ background: {p.accent_soft}; }}
QMenu {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {m.radius}px;
    padding: 4px;
}}
QMenu::item {{ padding: 5px 26px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.accent_soft}; color: {p.accent}; }}
QMenu::item:disabled {{ color: {p.text_disabled}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}
QToolTip {{
    background: {p.text};
    color: {p.surface};
    border: none;
    padding: 4px 6px;
    border-radius: 4px;
}}
QPushButton {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius}px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{ background: {p.surface_alt}; }}
QPushButton:pressed {{ background: {p.accent_soft}; }}
QPushButton:disabled {{ color: {p.text_disabled}; background: {p.surface_alt}; }}
QPushButton[accent="true"] {{
    background: {p.accent};
    color: #ffffff;
    border-color: {p.accent};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {p.accent_hover}; }}
QPushButton[accent="true"]:disabled {{ background: {p.accent_soft}; color: {p.text_disabled}; }}
QPushButton[flat="true"] {{ background: transparent; border-color: transparent; }}
QPushButton[flat="true"]:hover {{ background: {p.surface_alt}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius}px;
    padding: 4px 6px;
    selection-background-color: {p.accent};
    selection-color: #ffffff;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {p.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ background: {p.surface_alt}; color: {p.text_disabled}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    selection-background-color: {p.accent_soft};
    selection-color: {p.text};
    outline: none;
}}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator {{
    border: 1px solid {p.border_strong};
    border-radius: 3px;
    background: {p.surface};
}}
QCheckBox::indicator:checked {{
    background: {p.accent};
    border-color: {p.accent};
    image: none;
}}
QRadioButton::indicator {{
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    background: {p.surface};
}}
QRadioButton::indicator:checked {{ border: 5px solid {p.accent}; background: {p.surface}; }}
QGroupBox {{
    border: 1px solid {p.border};
    border-radius: {m.radius}px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {p.text_dim};
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {m.radius}px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{ padding: 4px 6px; border-radius: 4px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {p.accent_soft};
    color: {p.text};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {p.surface_alt}; }}
QHeaderView::section {{
    background: {p.surface_alt};
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
    padding: 5px 6px;
}}
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: {m.radius}px; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    border: 1px solid transparent;
    border-bottom: 2px solid transparent;
    padding: 6px 12px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ color: {p.accent}; border-bottom-color: {p.accent}; font-weight: 600; }}
QTabBar::tab:hover {{ background: {p.surface_alt}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.text_disabled}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {p.border_strong};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSlider::groove:horizontal {{
    height: 4px; background: {p.border}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p.accent};
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QProgressBar {{
    border: 1px solid {p.border};
    border-radius: {m.radius}px;
    background: {p.surface};
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{ background: {p.accent}; border-radius: {m.radius - 1}px; }}
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QScrollArea {{ border: none; background: transparent; }}
QDockWidget {{
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
    font-weight: 600;
}}
QDockWidget::title {{
    background: {p.surface};
    padding: 7px 10px;
    border-bottom: 1px solid {p.border};
}}
QColorDialog {{ background: {p.surface}; }}
QToolButton {{
    border: 1px solid transparent;
    border-radius: {m.radius}px;
}}
QToolButton:hover {{ background: {p.surface_alt}; border-color: {p.border}; }}
QToolButton:checked {{ background: {p.accent_soft}; border-color: {p.accent}; }}
QToolButton::menu-indicator {{ image: none; }}
QFrame[role="card"] {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {m.radius}px;
}}
QLabel[role="hint"] {{ color: {p.text_dim}; }}
QLabel[role="title"] {{ font-size: 12pt; font-weight: 600; }}
"""
