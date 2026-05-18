# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**QuantIDE** is a quantitative finance development platform built with **FastHTML + MonsterUI**. The project is currently in active architectural refactoring, consolidating around a FastHTML-based stack.

## Commands

```bash
# Install dependencies
poetry install

# Run the application
python -m quantide.app

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_*.py -v
```

Dependencies: Managed via Poetry (`pyproject.toml`).

## Architecture

The project is in active refactoring. Key components:

1. **Application Layer** — `quantide/app.py` is the main application entry point using FastHTML
2. **Core Modules** — `quantide/` contains core business logic
3. **Broker Abstraction** — Phase 2 focuses on broker abstraction convergence
4. **Data Layer** — Uses SQLite (via sqlite-utils) and Polars for data processing

## Key Configuration

| File | Purpose |
|------|---------|
| `pyproject.toml` | Project dependencies and metadata (Poetry) |
| `quantide/app.py` | FastHTML application entry point |
| `.dev/` | Development notes and architecture decision records |

## Development Status

- Project is in active refactoring (see `.dev/release_architecture_decision_v1.md`)
- Not using FastAPI + Vue (consolidating around FastHTML + MonsterUI)
- Release documentation in progress
- See `.dev/` for current architecture decisions and phase tracking

## Important Notes

- The project uses Python 3.13+
- Key dependencies: FastHTML, MonsterUI, Polars, loguru, cfg4py
- Database: SQLite with sqlite-utils
- Check `.dev/` directory for current development notes and architectural decisions
