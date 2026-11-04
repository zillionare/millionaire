"""Strategy scanning."""

from pathlib import Path as FilePath

from fasthtml.common import *
from fasthtml.common import (
    Div,
    Li,
    P,
    Path,
    Ul,
)
from fasthtml.svg import Path as SvgPath
from loguru import logger
from monsterui.all import *
from monsterui.all import (
    H3,
    Button,
    Input,
)

from quantide.service.discovery import strategy_loader
from quantide.web.pages.strategy_routes import (
    STRATEGY_MODAL_CLOSE_JS,
    rt,
)


def _scan_scope_list(scan_dirs: list[str]):
    """渲染策略扫描目录列表。"""
    return Ul(
        *[Li(path, cls="break-all") for path in scan_dirs],
        cls="list-disc pl-5 space-y-1 text-xs text-gray-500",
    )


def _strategy_scan_toolbar():
    """渲染策略扫描与示例复制工具栏。"""
    return Div(
        Button(
            Span(
                Svg(
                    SvgPath(
                        d="M12 4v16m8-8H4",
                        **{
                            "stroke-linecap": "round",
                            "stroke-linejoin": "round",
                            "stroke-width": "2",
                        },
                    ),
                    cls="w-5 h-5",
                    fill="none",
                    stroke="currentColor",
                    viewBox="0 0 24 24",
                ),
                cls="flex items-center",
            ),
            Span("扫描策略列表"),
            cls=(
                "px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412] "
                "inline-flex items-center gap-2 border-0 shadow-none"
            ),
            type="button",
            hx_post="/strategy/scan/run",
            hx_target="#modal-container",
        ),
        Button(
            Span("复制示例策略"),
            cls=(
                "px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 "
                "inline-flex items-center gap-2 border-0 shadow-none"
            ),
            type="button",
            title="复制内置示例到用户策略目录",
            hx_post="/strategy/scan/copy-examples",
            hx_target="#modal-container",
        ),
        Button(
            UkIcon("cog", size=20),
            cls=(
                "p-2 bg-transparent border-0 shadow-none text-gray-500 "
                "hover:text-gray-700 hover:bg-gray-100 rounded-lg inline-flex "
                "items-center justify-center"
            ),
            type="button",
            title="配置扫描目录",
            hx_get="/strategy/scan/config-modal",
            hx_target="#modal-container",
        ),
        cls="flex items-center gap-2",
    )


def _normalize_scan_directory(directory: str) -> tuple[str, Path]:
    """校验并标准化用户策略目录。"""
    text = directory.strip()
    if not text:
        raise ValueError("目录不能为空")

    path = FilePath(text).expanduser()
    if not path.is_absolute():
        raise ValueError("必须使用绝对路径，例如: /Users/name/strategies")

    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"目录不存在: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"路径不是目录: {path}")
    return str(path), path


@rt("/scan/config-modal")
def config_modal_route(req):
    scan_dir = strategy_loader.get_user_scan_directory()
    return _config_modal_html(scan_dir, is_error=False)


@rt("/scan/confirm")
def scan_confirm_modal(req):
    scan_dirs = strategy_loader.get_scan_directories()

    return Div(
        Div(
            Div(
                H3("确认扫描", cls="text-lg font-semibold text-gray-900 mb-4"),
                P("确定要扫描策略目录吗？", cls="text-gray-700"),
                P(
                    "系统会默认扫描内置示例目录，并合并您配置的用户目录。",
                    cls="text-sm text-gray-500 mt-2",
                ),
                Div(
                    P("当前扫描范围：", cls="text-sm text-gray-500 mt-2 mb-2"),
                    _scan_scope_list(scan_dirs),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "取消",
                        type="button",
                        cls="px-4 py-2 text-gray-600 hover:text-gray-800",
                        onclick=STRATEGY_MODAL_CLOSE_JS,
                    ),
                    Button(
                        "确定扫描",
                        type="button",
                        cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412] ml-2",
                        hx_post="/strategy/scan/run",
                        hx_target="#modal-container",
                    ),
                    cls="flex justify-end",
                ),
                cls="bg-white rounded-lg shadow-xl p-6 w-96",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
        ),
        id="scan-confirm-modal",
    )


@rt("/scan/run", methods=["POST"])
def run_scan(req):
    try:
        strategies = strategy_loader.scan_and_cache()
        strategy_count = len(strategies)
        scan_dirs = strategy_loader.get_scan_directories()
        if strategy_count == 0:
            return Div(
                Div(
                    Div(
                        H3("扫描完成", cls="text-lg font-semibold text-gray-900 mb-4"),
                        P("未发现任何策略", cls="text-gray-700 font-medium"),
                        Div(
                            P("本次扫描范围：", cls="text-sm text-gray-500 mt-2 mb-2"),
                            _scan_scope_list(scan_dirs),
                            cls="mb-4",
                        ),
                        Div(
                            Button(
                                "关闭",
                                type="button",
                                cls=(
                                    "px-4 py-2 bg-[#e41815] text-white rounded-lg "
                                    "hover:bg-[#c91412]"
                                ),
                                onclick=STRATEGY_MODAL_CLOSE_JS,
                            ),
                            cls="flex justify-end",
                        ),
                        cls="bg-white rounded-lg shadow-xl p-6 w-96",
                    ),
                    cls=(
                        "fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
                    ),
                ),
                id="scan-result-modal",
            )

        return Div(
            Div(
                Div(
                    H3("扫描完成", cls="text-lg font-semibold text-gray-900 mb-4"),
                    P(f"成功发现 {strategy_count} 个策略", cls="text-green-600 font-medium"),
                    P("内置示例目录已默认参与扫描", cls="text-sm text-gray-500 mt-2"),
                    Div(
                        P("本次扫描范围：", cls="text-sm text-gray-500 mt-2 mb-2"),
                        _scan_scope_list(scan_dirs),
                        cls="mb-4",
                    ),
                    P("策略列表将自动刷新", cls="text-sm text-gray-500 mt-2 mb-4"),
                    Div(
                        Button(
                            "关闭",
                            type="button",
                            cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412]",
                            onclick=STRATEGY_MODAL_CLOSE_JS,
                        ),
                        cls="flex justify-end",
                    ),
                    cls="bg-white rounded-lg shadow-xl p-6 w-96",
                ),
                cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
            ),
            Script("setTimeout(() => location.reload(), 1200);"),
            id="scan-result-modal",
        )
    except Exception as e:
        logger.error(f"Failed to scan strategies: {e}")
        return Div(
            Div(
                Div(
                    H3("扫描失败", cls="text-lg font-semibold text-gray-900 mb-4"),
                    P(f"错误: {str(e)}", cls="text-red-600 mb-4"),
                    Div(
                        Button(
                            "关闭",
                            type="button",
                            cls="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700",
                            onclick=STRATEGY_MODAL_CLOSE_JS,
                        ),
                        cls="flex justify-end",
                    ),
                    cls="bg-white rounded-lg shadow-xl p-6 w-96",
                ),
                cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
            ),
            id="scan-error-modal",
        )


def _config_modal_html(scan_dir: str, is_error: bool = False, error_message: str = ""):
    """配置对话框 HTML。"""
    title = "配置用户策略目录"
    builtin_dir = strategy_loader.get_builtin_scan_directory()
    if error_message:
        message = P(error_message, cls="text-red-600 mb-4")
    elif is_error:
        message = P("请输入有效的用户策略目录。", cls="text-red-600 mb-4")
    else:
        message = P(
            "这里仅用于设置用户策略目录；复制示例请回到策略列表页点击“复制示例策略”。",
            cls="text-sm text-gray-500 mb-4",
        )

    return Div(
        Div(
            Div(
                H3(title, cls="text-lg font-semibold text-gray-900 mb-4"),
                message,
                Div(
                    P("内置示例目录会始终参与扫描：", cls="text-sm text-gray-600"),
                    P(
                        builtin_dir,
                        cls=(
                            "mt-1 break-all rounded-lg bg-gray-50 px-3 py-2 font-mono "
                            "text-xs text-gray-500"
                        ),
                    ),
                    cls="mb-4",
                ),
                Div(
                    Input(
                        id="scan-dir-input",
                        value=scan_dir,
                        placeholder="请输入绝对路径，例如: /Users/name/strategies",
                        cls=(
                            "w-full px-3 py-2 border border-gray-300 rounded-lg "
                            "focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        ),
                    ),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "取消",
                        type="button",
                        cls="px-4 py-2 text-gray-600 hover:text-gray-800",
                        onclick=STRATEGY_MODAL_CLOSE_JS,
                    ),
                    Button(
                        "保存",
                        type="button",
                        cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412] ml-2",
                        hx_post="/strategy/scan/config",
                        hx_include="#scan-dir-input",
                        hx_target="#modal-container",
                    ),
                    cls="flex justify-end",
                ),
                cls="bg-white rounded-lg shadow-xl p-6 w-96",
            ),
            cls="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50",
        ),
        id="config-modal",
    )


@rt("/scan/config", methods=["POST"])
async def save_scan_config(req):
    directory = ""
    try:
        form = await req.form()
        directory = form.get("scan-dir-input", "").strip()
        directory, _ = _normalize_scan_directory(directory)

        strategy_loader.set_scan_directory(directory)

        return Modal(
            ModalTitle("配置已保存"),
            ModalBody(
                P(f"用户策略目录已设置为: {directory}", cls="text-green-600"),
                P("扫描时会同时包含内置示例目录。", cls="text-sm text-gray-500 mt-2"),
                P("页面即将刷新...", cls="text-sm text-gray-500 mt-2"),
            ),
            ModalFooter(
                Button(
                    "确定",
                    type="button",
                    cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412]",
                    onclick="location.reload()",
                ),
            ),
            id="config-success-modal",
        )
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        return _config_modal_html(
            directory,
            is_error=True,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to set scan directory: {e}")
        return _config_modal_html(
            directory,
            is_error=True,
            error_message=f"保存失败: {str(e)}",
        )


def _copy_requires_config_modal():
    """提示用户先配置策略目录。"""
    return Modal(
        ModalTitle("请先设置用户策略目录"),
        ModalBody(
            P("复制示例策略前，需要先配置用户策略目录。", cls="text-gray-600"),
            P(
                "点击下方“去设置”后，保存目录，再回来点击“复制示例策略”。",
                cls="text-sm text-gray-500 mt-2",
            ),
        ),
        ModalFooter(
            Button(
                "取消",
                type="button",
                cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200",
                onclick=STRATEGY_MODAL_CLOSE_JS,
            ),
            Button(
                "去设置",
                type="button",
                cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412]",
                hx_get="/strategy/scan/config-modal",
                hx_target="#modal-container",
            ),
        ),
        id="copy-requires-config-modal",
    )


@rt("/scan/copy-examples", methods=["POST"])
async def copy_scan_examples(req):
    """复制内置示例策略到用户目录。"""
    try:
        directory = strategy_loader.get_user_scan_directory().strip()
        if not directory:
            return _copy_requires_config_modal()

        directory, _ = _normalize_scan_directory(directory)
        result = strategy_loader.copy_examples_to_directory(directory)
        title = "示例已复制" if result.copied_count else "示例已存在"
        summary = (
            f"已复制 {result.copied_count} 个文件到: {directory}"
            if result.copied_count
            else f"目标目录已包含全部示例文件: {directory}"
        )

        return Modal(
            ModalTitle(title),
            ModalBody(
                P(summary, cls="text-green-600"),
                P(
                    f"已跳过 {result.skipped_count} 个同名文件，不会覆盖您的本地修改。",
                    cls="text-sm text-gray-500 mt-2",
                ),
                P(f"目标策略目录: {directory}", cls="text-sm text-gray-500 mt-2 break-all"),
            ),
            ModalFooter(
                Button(
                    "关闭",
                    type="button",
                    cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200",
                    onclick="location.reload()",
                ),
                Button(
                    "立即扫描",
                    type="button",
                    cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412]",
                    hx_post="/strategy/scan/run",
                    hx_target="#modal-container",
                ),
            ),
            id="copy-example-modal",
        )
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        return Modal(
            ModalTitle("复制失败"),
            ModalBody(
                P(str(e), cls="text-red-600"),
                P("请先检查当前用户策略目录配置。", cls="text-sm text-gray-500 mt-2"),
            ),
            ModalFooter(
                Button(
                    "去设置",
                    type="button",
                    cls="px-4 py-2 bg-[#e41815] text-white rounded-lg hover:bg-[#c91412]",
                    hx_get="/strategy/scan/config-modal",
                    hx_target="#modal-container",
                ),
            ),
            id="copy-example-error-modal",
        )
    except Exception as e:
        logger.error(f"Failed to copy example strategies: {e}")
        return Modal(
            ModalTitle("复制失败"),
            ModalBody(P(f"复制失败: {str(e)}", cls="text-red-600")),
            ModalFooter(
                Button(
                    "关闭",
                    type="button",
                    cls="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200",
                    onclick=STRATEGY_MODAL_CLOSE_JS,
                ),
            ),
            id="copy-example-error-modal",
        )
