"""Undo/redo basato su comandi, con descrizioni in italiano per la UI."""

from __future__ import annotations

from typing import Callable


class Command:
    """Un'operazione reversibile.

    Le sottoclassi implementano ``redo`` e ``undo``. ``merge_key`` permette di
    fondere comandi consecutivi identici (es. digitazione continua in un campo).
    """

    text: str = "Operazione"
    merge_key: str | None = None
    coalescable: bool = False

    def redo(self) -> None:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError

    def merge(self, other: "Command") -> bool:
        """Tenta di assorbire ``other``; True se la fusione è avvenuta."""
        return False

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        return f"<{type(self).__name__} {self.text}>"


class FunctionCommand(Command):
    """Comando generico che avvolge due callabel."""

    def __init__(self, text: str, do: Callable[[], None], undo: Callable[[], None]) -> None:
        self.text = text
        self._do = do
        self._undo = undo

    def redo(self) -> None:
        self._do()

    def undo(self) -> None:
        self._undo()


class MacroCommand(Command):
    """Raggruppa più comandi in un'unica voce dello stack."""

    def __init__(self, text: str, commands: list[Command]) -> None:
        self.text = text
        self.commands = list(commands)

    def redo(self) -> None:
        for c in self.commands:
            c.redo()

    def undo(self) -> None:
        for c in reversed(self.commands):
            c.undo()


class HistoryStack:
    """Stack di annullamento/ripetizione con raggruppamento opzionale."""

    def __init__(self, limit: int = 200, coalesce_ms: int = 600) -> None:
        self.limit = limit
        self.coalesce_ms = coalesce_ms
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._last_time: float = 0.0
        self._listeners: list[Callable[[], None]] = []
        self._suspended = 0

    def add_listener(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass

    def push(self, command: Command, do: bool = True) -> Command:
        """Registra un comando (ed lo esegue, salvo ``do=False``).

        In un contesto ``suspended`` il comando viene comunque eseguito ma non
        finisce nello stack: serve per gli aggiornamenti interni che non devono
        diventare passi di annullamento.
        """
        if self._suspended:
            if do:
                command.redo()
            return command
        now = _now()
        merged = False
        if (
            self._undo
            and do
            and command.coalescable
            and self._undo[-1].coalescable
            and self._undo[-1].merge_key == command.merge_key
            and (now - self._last_time) * 1000 <= self.coalesce_ms
        ):
            merged = self._undo[-1].merge(command)
        if not merged:
            if do:
                command.redo()
            self._undo.append(command)
            if len(self._undo) > self.limit:
                self._undo.pop(0)
        self._redo.clear()
        self._last_time = now
        self._notify()
        return command

    def do(self, command: Command) -> Command:
        return self.push(command, do=True)

    def run(self, command: Command) -> None:
        """Registra un comando già eseguito (non lo riesegue)."""
        self.push(command, do=False)

    def undo(self) -> Command | None:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._last_time = 0.0
        self._notify()
        return cmd

    def redo(self) -> Command | None:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        cmd.redo()
        self._undo.append(cmd)
        self._last_time = 0.0
        self._notify()
        return cmd

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._notify()

    @property
    def undo_cost(self) -> int:
        """Byte occupati dalle copie salvate dallo stack."""
        return sum(getattr(c, "byte_cost", 0) for c in self._undo)

    def trim(self, target_bytes: int) -> int:
        """Rimuove i comandi più vecchi finché il costo non rientra nel budget.

        Restituisce il numero di voci eliminate.
        """
        removed = 0
        while self._undo and self.undo_cost > target_bytes and len(self._undo) > 1:
            self._undo.pop(0)
            removed += 1
        if removed:
            self._notify()
        return removed

    def suspend(self) -> None:
        self._suspended += 1

    def resume(self) -> None:
        self._suspended = max(0, self._suspended - 1)

    class _SuspendCtx:
        def __init__(self, stack: "HistoryStack") -> None:
            self.stack = stack

        def __enter__(self) -> "HistoryStack._SuspendCtx":
            self.stack.suspend()
            return self

        def __exit__(self, *exc: object) -> None:
            self.stack.resume()

    def suspended(self) -> "HistoryStack._SuspendCtx":
        return HistoryStack._SuspendCtx(self)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_text(self) -> str:
        return self._undo[-1].text if self._undo else ""

    def redo_text(self) -> str:
        return self._redo[-1].text if self._redo else ""


def _now() -> float:
    import time

    return time.monotonic()
