"""Table shells for market datasets and compact account details."""

from collections.abc import Callable, Sequence
from typing import Any

from fasthtml.common import A, Div, Span, Table, Tbody, Th, Thead, Tr


def DatasetTable(
    headers: Sequence[object],
    rows: Sequence[object],
    *,
    column_classes: Sequence[str] | None = None,
    sticky_header: bool = False,
    aria_label: str | None = None,
) -> Any:
    header_classes = (
        "px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase whitespace-nowrap"
    )
    if sticky_header:
        header_classes += " sticky top-0 z-10 bg-gray-50"
    table_attrs: dict[str, Any] = {}
    if aria_label:
        table_attrs["aria_label"] = aria_label
    rendered_headers = []
    for index, label in enumerate(headers):
        extra = (
            column_classes[index]
            if column_classes is not None and index < len(column_classes)
            else ""
        )
        rendered_headers.append(Th(label, cls=f"{header_classes} {extra}".rstrip(), scope="col"))
    return Div(
        Table(
            Thead(Tr(*rendered_headers)),
            Tbody(*rows),
            cls="q-data-table min-w-full divide-y divide-gray-200",
            **table_attrs,
        ),
        cls=("overflow-auto max-h-[calc(100vh-300px)]" if sticky_header else "overflow-x-auto"),
    )


def AccountDetailTable(headers: Sequence[str], rows: Sequence[object]) -> Any:
    return Table(
        Thead(Tr(*[Th(label, cls="text-xs font-bold") for label in headers])),
        Tbody(*rows),
        cls=(
            "uk-table uk-table-divider uk-table-small uk-table-hover border "
            "border-gray-100 rounded-lg overflow-hidden"
        ),
    )


def pagination_button_class(active: bool) -> str:
    """Shared selected-page styling: red outline instead of filled emphasis."""
    return "q-btn q-btn--sm mx-0.5 " + (
        "bg-white text-[#e41815] border-[#e41815] font-semibold" if active else "border-black/20"
    )


def DatasetPagination(
    info: object,
    page: int,
    per_page: int,
    total_pages: int,
    url: Callable[[int, int], str],
    button_class: Callable[[bool], str],
) -> Any:
    return Div(
        Div(info, cls="text-sm text-gray-700"),
        Div(
            Span("每页: ", cls="text-sm text-gray-600 mr-1"),
            *[
                A(str(size), href=url(1, size), cls=button_class(size == per_page))
                for size in (20, 50, 100)
            ],
            cls="flex items-center ml-4",
        ),
        Div(
            *[
                A(str(number), href=url(number, per_page), cls=button_class(number == page))
                for number in range(max(1, page - 2), min(total_pages + 1, page + 3))
            ],
            cls="flex items-center ml-4",
        ),
        cls="px-4 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between",
    )
