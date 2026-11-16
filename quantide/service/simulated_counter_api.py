"""Loopback HTTP protocol for the CE demonstration counter."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from quantide.service.simulated_counter import SimulatedCounter


def create_counter_app(path: str | Path, **settings: Any) -> Starlette:
    """Create a counter with its own durable database and lifecycle."""
    counter = SimulatedCounter(path, **settings)

    async def endpoint(request: Request) -> JSONResponse:
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"error": "Simulation is loopback-only"}, status_code=403)
        try:
            if request.method == "GET":
                return JSONResponse({"mode": "simulated", "state": counter.snapshot()})
            payload = await request.json()
            operations: dict[str, Callable[[Any], dict[str, Any]]] = {
                "orders": counter.submit,
                "quotes": counter.quote,
                "cancel": counter.cancel,
            }
            return JSONResponse(operations[request.path_params["operation"]](payload))
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        try:
            yield
        finally:
            counter.close()

    app = Starlette(
        routes=[
            Route("/state", endpoint),
            Route("/{operation}", endpoint, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    app.state.counter = counter
    return app
