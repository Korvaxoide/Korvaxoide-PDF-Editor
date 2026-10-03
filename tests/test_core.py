"""Test del nucleo: geometria, unità, cronologia, ricerca, impaginazione del testo."""

from __future__ import annotations

import pymupdf
import pytest

from pdfeditor.core import geometry as geo
from pdfeditor.core import textlayout, units
from pdfeditor.core.history import HistoryStack, MacroCommand, Command


# ----------------------------------------------------------------- geometria


def test_rect_of_normalizza_ordine():
    r = geo.rect_of(100, 80, 20, 10)
    assert (r.x0, r.y0, r.x1, r.y1) == (20, 10, 100, 80)


def test_union_di_piu_riquadri():
    u = geo.union([pymupdf.Rect(0, 0, 10, 10), pymupdf.Rect(20, 5, 30, 40)])
    assert (u.x0, u.y0, u.x1, u.y1) == pytest.approx((0, 0, 30, 40))
    assert geo.union([]).is_empty


def test_clamp_rect_viene_tenuto_dentro():
    dentro = geo.clamp_rect(pymupdf.Rect(-20, -5, 200, 300), pymupdf.Rect(0, 0, 100, 200))
    assert dentro.x0 >= 0 and dentro.y0 >= 0
    assert dentro.x1 <= 100 and dentro.y1 <= 200


def test_aspect_limited_mantiene_proporzioni():
    r = geo.aspect_limited(pymupdf.Rect(0, 0, 200, 100), 0.5)
    assert r.width / r.height == pytest.approx(0.5, abs=1e-6)


def test_align_rects():
    rects = [pymupdf.Rect(0, 0, 10, 10), pymupdf.Rect(20, 10, 30, 20), pymupdf.Rect(50, 0, 60, 5)]
    sx = geo.align_rects(rects, "left")
    assert all(r.x0 == pytest.approx(0) for r in sx)
    dx = geo.align_rects(rects, "right")
    assert all(r.x1 == pytest.approx(60) for r in dx)


def test_distribute_rects_mantiene_i_lati_estremi():
    rects = [pymupdf.Rect(0, 0, 10, 10), pymupdf.Rect(20, 0, 30, 10), pymupdf.Rect(60, 0, 70, 10)]
    out = geo.distribute_rects(rects, "h")
    assert out[0].x0 == pytest.approx(0)
    assert out[-1].x1 == pytest.approx(70)
    assert out[1].width == pytest.approx(10)


def test_compute_snap_allinea_ai_bordi():
    page = pymupdf.Rect(0, 0, 200, 200)
    targets = [pymupdf.Rect(0, 50, 100, 60)]
    moving = pymupdf.Rect(41, 45, 61, 55)      # x0=41 vicino a 40 (centro target)
    res = geo.compute_snap(moving, targets, page, tol=4.0)
    assert res.snapped
    # il centro (51) si aggancia al centro 50 del riquadro di riferimento
    assert (res.x + 10) == pytest.approx(50.0)
    assert len(res.guides) >= 1


def test_compute_snap_disattivato():
    page = pymupdf.Rect(0, 0, 200, 200)
    moving = pymupdf.Rect(41, 45, 61, 55)
    res = geo.compute_snap(moving, [pymupdf.Rect(0, 50, 100, 60)], page, tol=4.0, guides_enabled=False)
    assert not res.snapped
    assert res.x == pytest.approx(41.0)


def test_rotazione_rettangolo():
    r = geo.Rect(0, 0, 10, 20)
    a = geo.rotate_point(0, 0, 0, 0, 90)
    assert a[0] == pytest.approx(0) and a[1] == pytest.approx(0)
    c = geo.quad_corners(r, 90)
    assert len(c) == 4


# -------------------------------------------------------------------- unita


def test_conversioni_unita():
    assert units.to_pt(1, "in") == pytest.approx(72.0)
    assert units.from_pt(72.0, "in") == pytest.approx(1.0)
    assert units.to_pt(25.4, "mm") == pytest.approx(72.0)
    assert "pt" in units.fmt(12.0, "pt")
    assert units.paper_size("A4")[0] == pytest.approx(595.28, abs=0.1)


# ---------------------------------------------------------------- cronologia


class _Add(Command):
    text = "Aggiungi"

    def __init__(self, store: list, value: int) -> None:
        self.store, self.value = store, value

    def redo(self) -> None:
        self.store.append(self.value)

    def undo(self) -> None:
        self.store.remove(self.value)


def test_undo_redo_base():
    store: list[int] = []
    h = HistoryStack()
    h.do(_Add(store, 1))
    h.do(_Add(store, 2))
    assert store == [1, 2]
    h.undo()
    assert store == [1]
    h.redo()
    assert store == [1, 2]
    # dopo il ripeti la pila e' ancora indietro di un passo: «not ... is False»
    # era una doppia negazione che passava anche con can_undo falso
    assert h.can_undo, "dopo il ripeti deve restare qualcosa da annullare"
    assert not h.can_redo, "dopo il ripeti non deve restare nulla da ripetere"
    assert h.undo_text() == "Aggiungi"


def test_undo_invalida_redo():
    store: list[int] = []
    h = HistoryStack()
    h.do(_Add(store, 1))
    h.undo()
    h.do(_Add(store, 2))
    assert h.can_redo is False


def test_macro_command_annulla_tutto():
    store: list[int] = []
    h = HistoryStack()
    h.do(MacroCommand("Gruppo", [_Add(store, 1), _Add(store, 2)]))
    assert store == [1, 2]
    h.undo()
    assert store == []


def test_suspend_non_registra():
    store: list[int] = []
    h = HistoryStack()
    with h.suspended():
        h.do(_Add(store, 1))
    assert store == [1]
    assert h.can_undo is False


def test_limit_stack_scarta_i_comandi_vecchi():
    store: list[int] = []
    h = HistoryStack(limit=3)
    for i in range(6):
        h.do(_Add(store, i))
    # gli effetti restano, ma la cronologia conserva solo gli ultimi
    assert len(h._undo) == 3
    assert store == [0, 1, 2, 3, 4, 5]


# ----------------------------------------------------------------- testo


def test_wrap_rispetta_larghezza():
    lines = textlayout.wrap("una frase abbastanza lunga da andare a capo", "helv", 12, 60)
    assert len(lines) > 1
    for ln in lines:
        assert textlayout.text_width(ln, "helv", 12) <= 60 + 1 or " " not in ln


def test_wrap_preserva_i_ritorni_espliciti():
    assert textlayout.wrap("a\nb\nc", "helv", 12, 500) == ["a", "b", "c"]


def test_layout_riporta_il_trasbordo():
    testo = "riga\n" * 10
    dentro = textlayout.layout_text(testo, "helv", 12, 200, 400)
    fuori = textlayout.layout_text(testo, "helv", 12, 200, 20)
    assert dentro.overflow is False
    assert fuori.overflow is True


def test_fit_fontsize_riduce_il_corpo():
    testo = "testo piu' lungo" * 6
    size = textlayout.fit_fontsize(testo, "helv", 24, 100, 40)
    assert 4.0 <= size < 24.0


def test_required_size_cresce_con_il_corpo():
    w1, h1 = textlayout.required_size("abc", "helv", 10, 500)
    w2, h2 = textlayout.required_size("abc", "helv", 20, 500)
    assert w2 > w1 and h2 > h1


def test_text_rects_allineamento():
    r = textlayout.text_rects("centrato", "helv", 12, pymupdf.Rect(0, 0, 200, 40), align=1)
    assert len(r) == 1
    assert r[0].x0 > 0
