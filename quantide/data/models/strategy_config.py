"""策略配置和扫描结果数据模型 (v0.2 spec)"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from quantide.data.models.base import Entity, new_uuid_id


@dataclass
class ParamSpec:
    """v0.2: default_config 中单个参数的类型契约

    v0.2 范围: name + default 必填; type_hint / description / constraints 暂为 None
    """

    name: str
    default: object = None
    type_hint: object = None  # v0.2 始终 None
    description: object = None  # v0.2 始终 None
    constraints: object = None  # v0.2 始终 None


# SkipReason 枚举值(对齐 spec FR-020 容错表)
SKIP_PERMISSION_DENIED = "PermissionDenied"
SKIP_SYNTAX_ERROR = "SyntaxError"
SKIP_IMPORT_ERROR = "ImportError"
SKIP_MODULE_INIT_ERROR = "ModuleInitError"
SKIP_NOT_A_STRATEGY = "NotAStrategy"
SKIP_INVALID_CONFIG = "InvalidConfig"
SKIP_BUILTIN_OVERRIDDEN = "BuiltinOverridden"


@dataclass
class StrategyMetadata:
    """v0.2: 单个策略的元数据 (from spec FR-020)"""

    strategy_id: str
    name: str
    description: str
    strategy_type: Literal["independent", "risk"]
    module: str
    is_builtin: bool
    default_config: dict  # dict[str, ParamSpec]
    skipped_reasons: list  # list[SkippedEntry], 此策略的 skip 原因


@dataclass
class SkippedEntry:
    """v0.2: 枚举跳过的项 (from spec FR-020)"""

    path: str  # 文件路径
    class_name: str | None  # 类名, 文件级失败时为 None
    reason: str  # SkippedReason 值
    detail: str  # 原因详情


@dataclass
class EnumerationResult:
    """v0.2: 枚举结果 (from spec FR-020)"""

    strategies: list  # list[StrategyMetadata]
    diagnostics: list  # list[SkippedEntry]


@dataclass
class StrategyConfig(Entity):
    """策略扫描配置"""

    __table_name__ = "strategy_config"
    __pk__ = "id"
    __indexes__ = (["key"], True)  # key 唯一

    id: str = field(default_factory=new_uuid_id)
    key: str = ""  # 配置键，如 'scan_directory'
    value: str = ""  # 配置值
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class StrategyInfo(Entity):
    """扫描发现的策略信息"""

    __table_name__ = "strategy_info"
    __pk__ = "id"
    __indexes__ = (["name"], True)  # 策略名唯一

    id: str = field(default_factory=new_uuid_id)
    name: str = ""  # 策略类名
    module_path: str = ""  # 模块路径
    file_path: str = ""  # 文件路径
    description: str = ""  # 策略描述
    version: str = "1.0.0"  # 版本号
    params: str = ""  # 参数配置(JSON)
    scan_dir: str = ""  # 扫描目录
    scanned_at: datetime = field(default_factory=datetime.now)
    strategy_type: str = "independent"  # "independent" | "risk"
