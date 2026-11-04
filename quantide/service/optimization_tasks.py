"""参数优化任务管理：后台执行、进度、中断与历史留存。"""

from __future__ import annotations

import datetime
import json
import threading
import traceback
from typing import Any

from loguru import logger

from quantide.data.sqlite import db
from quantide.service.param_optimizer import (
    OBJECTIVE_LABELS,
    OptimizationSpec,
    ParamOptimizer,
    new_task_id,
    rank_results,
)

OPTIMIZATION_TABLE = "optimization_runs"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"


def _init_table() -> None:
    """初始化任务表。"""
    if OPTIMIZATION_TABLE in db.table_names():
        _drop_placeholder_row()
        return
    db[OPTIMIZATION_TABLE].create(
        {
            "task_id": str,
            "strategy_name": str,
            "spec": str,
            "status": str,
            "objective": str,
            "total": int,
            "done": int,
            "results": str,
            "started_at": str,
            "finished_at": str,
            "error": str,
        },
        pk="task_id",
        if_not_exists=True,
    )


def _drop_placeholder_row() -> None:
    """删除早期版本用于建表的占位行。"""
    try:
        db[OPTIMIZATION_TABLE].delete_where("task_id = ?", ("init",))
    except Exception:  # pragma: no cover - 清理失败不影响主流程
        pass


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    try:
        spec = json.loads(row.get("spec") or "{}")
    except (TypeError, ValueError):
        spec = {}
    try:
        results = json.loads(row.get("results") or "[]")
    except (TypeError, ValueError):
        results = []
    return {
        "task_id": row.get("task_id", ""),
        "strategy_name": row.get("strategy_name", ""),
        "spec": spec,
        "status": row.get("status", STATUS_PENDING),
        "objective": row.get("objective", "sharpe"),
        "total": int(row.get("total") or 0),
        "done": int(row.get("done") or 0),
        "results": results,
        "started_at": row.get("started_at", ""),
        "finished_at": row.get("finished_at", ""),
        "error": row.get("error", ""),
    }


class _RunningTask:
    """内存中的运行中任务。"""

    def __init__(self, spec: OptimizationSpec) -> None:
        self.spec = spec
        self.optimizer = ParamOptimizer(spec)
        self.done = 0
        self.total = 0
        self.results: list[dict[str, Any]] = []
        self.error = ""
        self.thread: threading.Thread | None = None


_RUNNING: dict[str, _RunningTask] = {}
_FINISHED: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _save(
    task_id: str,
    spec: OptimizationSpec,
    status: str,
    total: int,
    done: int,
    results: list[dict[str, Any]],
    error: str = "",
    finished_at: str = "",
) -> None:
    """写入任务状态（落库失败不影响内存态）。"""
    try:
        _save_to_db(
            task_id,
            spec,
            status,
            total,
            done,
            results,
            error=error,
            finished_at=finished_at,
        )
    except Exception as exc:  # pragma: no cover - 数据库异常兜底
        logger.warning(f"参数优化任务状态落库失败: {exc}")


def _save_to_db(
    task_id: str,
    spec: OptimizationSpec,
    status: str,
    total: int,
    done: int,
    results: list[dict[str, Any]],
    error: str = "",
    finished_at: str = "",
) -> None:
    """写入任务状态。"""
    _init_table()
    payload = json.dumps(results, ensure_ascii=False, default=str)
    db[OPTIMIZATION_TABLE].insert(
        {
            "task_id": task_id,
            "strategy_name": spec.strategy_name,
            "spec": json.dumps(spec.to_dict(), ensure_ascii=False, default=str),
            "status": status,
            "objective": spec.objective,
            "total": int(total),
            "done": int(done),
            "results": payload,
            "started_at": datetime.datetime.now().isoformat(),
            "finished_at": finished_at or datetime.datetime.now().isoformat(),
            "error": error,
        },
        pk="task_id",
        replace=True,
    )


def start_optimization(spec: OptimizationSpec) -> str:
    """启动一个参数优化任务（后台线程）。

    Args:
        spec: 优化配置。

    Returns:
        str: 任务 ID。
    """
    task_id = new_task_id()
    running = _RunningTask(spec)
    with _LOCK:
        _RUNNING[task_id] = running
    _save(task_id, spec, STATUS_PENDING, 0, 0, [])

    def _worker() -> None:
        def _progress(done: int, total: int, result: dict[str, Any]) -> None:
            running.done = done
            running.total = total
            running.results.append(result)
            _save(task_id, spec, STATUS_RUNNING, total, done, running.results)

        try:
            _save(task_id, spec, STATUS_RUNNING, 0, 0, [])
            results = running.optimizer.run(on_progress=_progress)
            ranked = rank_results(results, spec.objective)
            status = STATUS_CANCELLED if running.optimizer.cancelled else STATUS_DONE
            _save(
                task_id,
                spec,
                status,
                running.total or len(results),
                len(results),
                ranked,
                finished_at=datetime.datetime.now().isoformat(),
            )
            with _LOCK:
                _FINISHED[task_id] = {
                    "task_id": task_id,
                    "strategy_name": spec.strategy_name,
                    "spec": spec.to_dict(),
                    "status": status,
                    "objective": spec.objective,
                    "total": running.total or len(results),
                    "done": len(results),
                    "results": ranked,
                    "started_at": "",
                    "finished_at": datetime.datetime.now().isoformat(),
                    "error": running.error,
                }
        except Exception as exc:  # pragma: no cover - 后台任务兜底
            logger.error(f"参数优化任务失败: {exc}\n{traceback.format_exc()}")
            running.error = str(exc)
            _save(
                task_id,
                spec,
                STATUS_FAILED,
                running.total,
                running.done,
                running.results,
                error=str(exc),
            )
        finally:
            with _LOCK:
                _RUNNING.pop(task_id, None)

    thread = threading.Thread(target=_worker, name=f"optimize-{task_id[:8]}", daemon=True)
    running.thread = thread
    thread.start()
    return task_id


def cancel_optimization(task_id: str) -> bool:
    """请求中断一个运行中的优化任务。

    Args:
        task_id: 任务 ID。

    Returns:
        bool: 是否找到了运行中的任务并已请求中断。
    """
    with _LOCK:
        running = _RUNNING.get(task_id)
    if running is None:
        return False
    running.optimizer.cancel()
    return True


def get_task(task_id: str) -> dict[str, Any] | None:
    """读取任务状态。

    Args:
        task_id: 任务 ID。

    Returns:
        dict | None: 任务信息。
    """
    with _LOCK:
        running = _RUNNING.get(task_id)
        finished = _FINISHED.get(task_id)
    if running is None and finished is not None:
        return dict(finished)
    if running is not None:
        return {
            "task_id": task_id,
            "strategy_name": running.spec.strategy_name,
            "spec": running.spec.to_dict(),
            "status": STATUS_RUNNING,
            "objective": running.spec.objective,
            "total": running.total,
            "done": running.done,
            "results": running.results,
            "started_at": "",
            "finished_at": "",
            "error": running.error,
        }
    _init_table()
    rows = list(db[OPTIMIZATION_TABLE].rows_where("task_id = ?", (task_id,)))
    if not rows:
        return None
    return _row_to_dict(dict(rows[0]))


def list_tasks(strategy_name: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """列出历史任务（最近的在前）。

    Args:
        strategy_name: 只看某个策略；为空则全部。
        limit: 返回条数。

    Returns:
        list[dict]: 任务列表。
    """
    _init_table()
    if strategy_name:
        rows = list(
            db[OPTIMIZATION_TABLE].rows_where(
                "strategy_name = ?", (strategy_name,), order_by="started_at desc", limit=limit
            )
        )
    else:
        rows = list(db[OPTIMIZATION_TABLE].rows_where(order_by="started_at desc", limit=limit))
    return [_row_to_dict(dict(row)) for row in rows]


def objective_label(objective: str) -> str:
    """目标函数的中文名。"""
    return OBJECTIVE_LABELS.get(objective, objective)


def shutdown_optimizations() -> None:
    """Cancel active optimizers and wait for bounded, cooperative termination."""
    with _LOCK:
        tasks = list(_RUNNING.values())
    for task in tasks:
        task.optimizer.cancel()
    for task in tasks:
        thread = getattr(task, "thread", None)
        if thread is not None:
            thread.join()
