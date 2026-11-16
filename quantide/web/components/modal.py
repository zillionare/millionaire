"""Shared viewport and backdrop for accessible application dialogs."""

from fasthtml.common import FT, Div


def ModalBackdrop() -> FT:
    return Div(cls="fixed inset-0 bg-black/50 transition-opacity")


def ModalViewport(panel: FT, alignment: str) -> FT:
    return Div(Div(panel, cls=alignment), cls="fixed inset-0 z-10 overflow-y-auto")
