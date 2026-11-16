"""Breadcrumbs for the system maintenance section."""

from fasthtml.common import FT, A, Div, Nav, Span


def SystemBreadcrumb(title: str) -> FT:
    return Div(
        Nav(
            A("首页", href="/", cls="hover:text-[#e41815]"),
            Span(">", cls="text-gray-400"),
            A("系统维护", href="/system/", cls="hover:text-[#e41815]"),
            Span(">", cls="text-gray-400"),
            Span(title, cls="text-gray-900 font-medium"),
            cls="flex w-fit items-center justify-start space-x-2 text-sm text-gray-600",
        ),
        cls="mb-4",
    )
