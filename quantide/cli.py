"""Run the installed Millionaire web application."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
import time
import webbrowser
from typing import Any

import uvicorn

from quantide.service.research_cli import (
    backtest_run_payload,
    check_factor,
    data_status,
    envelope,
    envelope_json,
    init_factor,
    list_factors,
    preset_list_payload,
    preset_save_payload,
    run_study,
)


def _truthy(value: str | None) -> bool:
    """Return whether an environment flag is enabled."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _open_browser(url: str) -> None:
    """Open the local app after the server has had time to bind."""
    time.sleep(1.0)
    webbrowser.open(url)


def _run_web(args: argparse.Namespace) -> int:
    from quantide.config.server_address import effective_address, publish_port

    host, port = effective_address(args.host, args.port)
    publish_port(port)
    if args.open_browser:
        threading.Thread(
            target=_open_browser, args=(f"http://127.0.0.1:{port}",), daemon=True
        ).start()
    uvicorn.run("quantide.app:app", host=host, port=port, reload=args.reload)
    return 0


def _add_data_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    data = commands.add_parser("data", help="inspect the active market data")
    data_commands = data.add_subparsers(dest="data_command")
    status = data_commands.add_parser("status", help="show data coverage and schema")
    status.add_argument("--json", action="store_true")


def _add_factor_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    factor = commands.add_parser("factor", help="list, create, check and study factors")
    factor_commands = factor.add_subparsers(dest="factor_command")
    factor_list = factor_commands.add_parser("list", help="list discovered factors")
    factor_list.add_argument("--json", action="store_true")
    factor_init = factor_commands.add_parser("init", help="create a factor plugin template")
    factor_init.add_argument("factor_id")
    factor_init.add_argument("--group", default="自定义因子")
    factor_init.add_argument("--dir")
    factor_init.add_argument("--json", action="store_true")
    factor_check = factor_commands.add_parser("check", help="run the factor wind tunnel")
    factor_check.add_argument("target", metavar="PATH_OR_FACTOR_ID")
    factor_check.add_argument("--cutoff", action="append", default=[], metavar="YYYY-MM-DD")
    factor_check.add_argument("--start", metavar="YYYY-MM-DD")
    factor_check.add_argument("--end", metavar="YYYY-MM-DD")
    factor_check.add_argument("--json", action="store_true")
    factor_study = factor_commands.add_parser("study", help="run factor IC research")
    factor_study.add_argument("factor_id")
    factor_study.add_argument("--start", required=True, metavar="YYYY-MM-DD")
    factor_study.add_argument("--end", required=True, metavar="YYYY-MM-DD")
    factor_study.add_argument("--holdings", default="1,3,5")
    factor_study.add_argument("--price", choices=["open", "close"], default="open")
    factor_study.add_argument("--json", action="store_true")


def _add_preset_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    preset = commands.add_parser("preset", help="manage factor presets")
    preset_commands = preset.add_subparsers(dest="preset_command")
    preset_list = preset_commands.add_parser("list", help="list saved presets")
    preset_list.add_argument("--json", action="store_true")
    preset_save = preset_commands.add_parser("save", help="validate and save a preset")
    preset_save.add_argument("--id", required=True, dest="preset_id")
    preset_save.add_argument("--name", required=True)
    preset_save.add_argument("--features", required=True)
    preset_save.add_argument(
        "--label-kind", choices=["raw_return", "excess_mean", "cs_rank"], default="raw_return"
    )
    preset_save.add_argument("--params", default="{}")
    preset_save.add_argument("--json", action="store_true")


def _add_backtest_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    backtest = commands.add_parser("backtest", help="run research backtests")
    backtest_commands = backtest.add_subparsers(dest="backtest_command")
    backtest_run = backtest_commands.add_parser("run", help="run one strategy backtest")
    backtest_run.add_argument("--strategy", required=True)
    source = backtest_run.add_mutually_exclusive_group()
    source.add_argument("--preset")
    source.add_argument("--params")
    backtest_run.add_argument("--start", required=True, metavar="YYYY-MM-DD")
    backtest_run.add_argument("--end", required=True, metavar="YYYY-MM-DD")
    backtest_run.add_argument("--ablation-vs", metavar="BASELINE_PRESET_ID")
    backtest_run.add_argument("--initial-cash", type=float, default=1_000_000.0)
    backtest_run.add_argument("--json", action="store_true")


def _add_risk_extension_parsers(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    risk = commands.add_parser(
        "risk-extension", help="enable a persistent user risk-program extension"
    )
    risk.add_argument("action", choices=["enable", "disable", "status"])
    risk.add_argument("--copy-example", action="store_true")
    risk.add_argument("--json", action="store_true")


def _add_research_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    _add_data_parsers(commands)
    _add_factor_parsers(commands)
    _add_preset_parsers(commands)
    _add_backtest_parsers(commands)
    _add_risk_extension_parsers(commands)


def _params_json(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise ValueError("--params 必须是合法 JSON 对象") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--params 必须是 JSON 对象")
    return parsed


def _date(value: str | None, *, default: dt.date | None = None) -> dt.date | None:
    if value is None:
        return default
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"非法日期: {value}") from exc


def _holdings(value: str) -> list[int]:
    try:
        holdings = [int(item) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError("--holdings 必须是逗号分隔的整数") from exc
    if not holdings:
        raise ValueError("--holdings 不能为空")
    return holdings


def _emit_risk_extension(payload: dict[str, Any], data: dict[str, Any]) -> None:
    if not payload.get("ok"):
        diagnostics = payload.get("diagnostics") or [{}]
        print(f"{payload.get('status')}: {diagnostics[0].get('message')}")
        return
    print(f"Risk extension: {'enabled' if data.get('enabled') else 'disabled'}")
    print(f"Extension: {data.get('extension_path')}")
    print(f"State: {data.get('state_path')}")
    if data.get("copied_example"):
        print("Copied the teaching example.")
    if data.get("restart_required"):
        print("Restart the background service to apply this change.")


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(envelope_json(payload))
        return
    data = payload.get("data") or {}
    if str(payload.get("command", "")).startswith("risk-extension."):
        _emit_risk_extension(payload, data)
        return
    if payload.get("status") in {"PASS", "FAIL", "INCONCLUSIVE"}:
        print(f"{payload.get('status')}  {data.get('factor_id') or ''}".rstrip())
        for item in payload.get("diagnostics") or []:
            print(f"- {item.get('code')}: {item.get('message')}")
        return
    print(envelope_json(payload))


def _command_name(args: argparse.Namespace) -> str:
    if args.command == "data":
        return f"data.{args.data_command}"
    if args.command == "preset":
        return f"preset.{args.preset_command}"
    if args.command == "backtest":
        return f"backtest.{args.backtest_command}"
    if args.command == "risk-extension":
        return f"risk-extension.{args.action}"
    return f"factor.{args.factor_command}"


def _data_status_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    return (
        envelope(
            "data.status",
            ok=True,
            status="OK",
            exit_code=0,
            data=data_status(),
        ),
        0,
    )


def _factor_list_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    return envelope("factor.list", ok=True, status="OK", exit_code=0, data=list_factors()), 0


def _factor_init_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    data = init_factor(args.factor_id, group=args.group, directory=args.dir)
    return envelope("factor.init", ok=True, status="OK", exit_code=0, data=data), 0


def _factor_check_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    cutoffs = [value for value in map(_date, args.cutoff) if value is not None]
    return check_factor(
        args.target,
        cutoffs=cutoffs or None,
        start=_date(args.start),
        end=_date(args.end),
    )


def _factor_study_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    return run_study(
        args.factor_id,
        start=_date(args.start) or dt.date.today(),
        end=_date(args.end) or dt.date.today(),
        holdings=_holdings(args.holdings),
        price_field=args.price,
    )


def _preset_list_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    return envelope("preset.list", ok=True, status="OK", exit_code=0, data=preset_list_payload()), 0


def _preset_save_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    features = [item.strip() for item in args.features.split(",") if item.strip()]
    data = preset_save_payload(
        args.preset_id,
        args.name,
        features,
        label_kind=args.label_kind,
        params=_params_json(args.params),
    )
    return envelope("preset.save", ok=True, status="OK", exit_code=0, data=data), 0


def _risk_extension_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    from quantide.providers.risk_extensions import (
        configure_risk_extension,
        risk_extension_status,
    )

    data = (
        risk_extension_status()
        if args.action == "status"
        else configure_risk_extension(args.action == "enable", copy_example=bool(args.copy_example))
    )
    return (
        envelope(
            f"risk-extension.{args.action}",
            ok=True,
            status="OK",
            exit_code=0,
            data=data,
        ),
        0,
    )


def _backtest_run_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    start = _date(args.start)
    end = _date(args.end)
    if start is None or end is None:
        raise ValueError("--start 与 --end 必须是有效日期")
    data = backtest_run_payload(
        args.strategy,
        start=start,
        end=end,
        preset_id=args.preset,
        params=_params_json(args.params),
        ablation_vs=args.ablation_vs,
        initial_cash=args.initial_cash,
    )
    return envelope("backtest.run", ok=True, status="OK", exit_code=0, data=data), 0


_COMMANDS = {
    ("data", "status"): _data_status_command,
    ("factor", "list"): _factor_list_command,
    ("factor", "init"): _factor_init_command,
    ("factor", "check"): _factor_check_command,
    ("factor", "study"): _factor_study_command,
    ("preset", "list"): _preset_list_command,
    ("preset", "save"): _preset_save_command,
    ("backtest", "run"): _backtest_run_command,
    ("risk-extension", "enable"): _risk_extension_command,
    ("risk-extension", "disable"): _risk_extension_command,
    ("risk-extension", "status"): _risk_extension_command,
}


def _error_payload(command: str, exc: Exception) -> tuple[dict[str, Any], int]:
    message = str(exc)
    insufficient = isinstance(exc, ValueError) and any(
        marker in message for marker in ("没有可用行情", "日线为空", "样本不足")
    )
    exit_code = 4 if insufficient else 2
    payload = envelope(
        command,
        ok=False,
        status="INCONCLUSIVE" if insufficient else "ERROR",
        exit_code=exit_code,
        diagnostics=[
            {
                "code": "INSUFFICIENT_DATA" if insufficient else "INVALID_REQUEST",
                "message": message,
            }
        ],
    )
    return payload, exit_code


def _run_research(args: argparse.Namespace) -> int:
    from quantide.config.paths import get_app_db_path
    from quantide.data.sqlite import db

    if not db._initialized:
        db.init(get_app_db_path())
    command = _command_name(args)
    subcommand = {
        "data": getattr(args, "data_command", None),
        "factor": getattr(args, "factor_command", None),
        "preset": getattr(args, "preset_command", None),
        "backtest": getattr(args, "backtest_command", None),
        "risk-extension": getattr(args, "action", None),
    }.get(args.command)
    handler = _COMMANDS.get((str(args.command), str(subcommand or "")))
    if handler is None:
        print("缺少子命令", file=sys.stderr)
        return 2
    try:
        payload, exit_code = handler(args)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        payload, exit_code = _error_payload(command, exc)
    _emit(payload, getattr(args, "json", False))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    """Start Uvicorn and optionally open the local app in a browser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None)
    parser.add_argument(
        "--port",
        type=int,
        default=None,
    )
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--stub",
        action="store_true",
        help="enable development stubs (requires a source checkout)",
    )
    parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="open the local app in the default browser after startup",
    )
    parser.add_argument(
        "--no-browser",
        dest="open_browser",
        action="store_false",
        help="disable QUANTIDE_OPEN_BROWSER for this run",
    )
    parser.set_defaults(open_browser=_truthy(os.getenv("QUANTIDE_OPEN_BROWSER")))
    commands = parser.add_subparsers(dest="command")
    service = commands.add_parser("service", help="manage the native background service")
    service.add_argument("action", choices=["install", "start", "stop", "status", "uninstall"])
    service.add_argument("--system", action="store_true", help="use a macOS LaunchDaemon")
    service.add_argument("--user", help="non-root account for a macOS system service")
    control = commands.add_parser("control", help="open the foreground service controller")
    registration = control.add_mutually_exclusive_group()
    registration.add_argument("--install", action="store_true", help="register the macOS menu")
    registration.add_argument("--uninstall", action="store_true", help="remove the macOS menu")
    control.add_argument("--system", action="store_true", help="control a macOS system service")
    counter = commands.add_parser(
        "simulated-counter", help="run the loopback demonstration counter"
    )
    counter.add_argument("--database", required=True)
    counter.add_argument("--listen-port", type=int, default=8131)
    commands.add_parser("web-url", help="print the local web interface URL")
    provider = commands.add_parser(
        "quote-provider", help="enable a persistent user quote extension"
    )
    provider.add_argument("action", choices=["enable", "disable", "status"])
    _add_research_parsers(commands)
    args = parser.parse_args(argv)

    if args.command in {"data", "factor", "preset", "backtest", "risk-extension"}:
        return _run_research(args)
    if args.command == "web-url":
        from quantide.config.server_address import controller_url

        print(controller_url())
        return 0
    if args.command == "quote-provider":
        from quantide.providers.extensions import manage_quote_provider

        return manage_quote_provider(args.action)
    if args.command == "service":
        from quantide.service.host_service import manage_service

        return manage_service(args.action, system=args.system, user=args.user)
    if args.command == "control":
        from quantide.service.desktop_control import main as control_main

        return int(control_main(install=args.install, uninstall=args.uninstall, system=args.system))
    if args.command == "simulated-counter":
        from quantide.service.simulated_counter_api import create_counter_app

        uvicorn.run(create_counter_app(args.database), host="127.0.0.1", port=args.listen_port)
        return 0

    if args.stub:
        os.environ["QUANTIDE_ENABLE_DEV_STUBS"] = "1"

    return _run_web(args)


if __name__ == "__main__":
    raise SystemExit(main())
