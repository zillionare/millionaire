"""v0.2-003-coverage FR-0101 AC-1..AC-5 pytest configuration contract."""

from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_pyproject() -> dict:
    """Load the project TOML configuration from the repository root.

    Returns:
        Parsed pyproject configuration.

    Raises:
        TOMLDecodeError: If the configuration is invalid TOML.
    """
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as config_file:
        return tomllib.load(config_file)


def test_pytest_configuration_enables_asyncio_auto_mode() -> None:
    """FR-0101 AC-5: pytest config declares automatic asyncio handling."""
    configuration = load_pyproject()

    pytest_options = configuration["tool"]["pytest"]["ini_options"]

    assert pytest_options["asyncio_mode"] == "auto"


def test_pytest_configuration_does_not_override_unit_test_command() -> None:
    """FR-0101 AC-1: testpaths, if configured, remains tests/unit only."""
    configuration = load_pyproject()

    testpaths = configuration["tool"]["pytest"]["ini_options"].get("testpaths")

    assert testpaths in (None, ["tests/unit"])


def test_project_has_no_duplicate_pytest_configuration_files() -> None:
    """FR-0101 AC-5: pyproject.toml is the sole pytest config source."""
    duplicate_configurations = [
        filename
        for filename in ("pytest.ini", "setup.cfg", "tox.ini")
        if (PROJECT_ROOT / filename).exists()
    ]

    assert duplicate_configurations == []


def test_coverage_configuration_targets_quantide() -> None:
    """FR-0101 AC-1: coverage collection uses the quantide package."""
    configuration = load_pyproject()

    assert configuration["tool"]["coverage"]["run"]["source"] == ["quantide"]


def test_coverage_configuration_enables_branch_coverage() -> None:
    """FR-0101 AC-4: coverage data includes branch execution information."""
    configuration = load_pyproject()

    assert configuration["tool"]["coverage"]["run"]["branch"] is True


def test_coverage_configuration_tracks_multiprocessing_subprocesses() -> None:
    """AC-NFR1201-03: subprocess workers emit parallel data using the shared config."""
    run = load_pyproject()["tool"]["coverage"]["run"]

    assert run["parallel"] is True
    assert run["concurrency"] == ["multiprocessing"]
    assert run["patch"] == ["subprocess"]
