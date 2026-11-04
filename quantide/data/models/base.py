"""数据模型基类"""

import types
import uuid
from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any, ClassVar, Union, cast, get_args, get_origin


def new_uuid_id() -> str:
    return "qtide-" + uuid.uuid4().hex[:16]


def _sqlite_field_type(field_type: Any) -> type[Any]:
    """Preserve primitive storage, nullable unions and integer enum values."""
    primitives = (str, int, float, bool)
    if field_type in primitives:
        return cast(type[Any], field_type)
    if get_origin(field_type) is Union or isinstance(field_type, types.UnionType):
        non_none = [item for item in get_args(field_type) if item is not type(None)]
        return cast(type[Any], non_none[0]) if non_none and non_none[0] in primitives else str
    if isinstance(field_type, type) and issubclass(field_type, Enum):
        return int
    return str


@dataclass
class Entity:
    """模型基类，提供数据库操作方法， 提供转换为数据库 schema 字典的方法"""

    __table_name__: ClassVar[str]
    __pk__: ClassVar[str | list[str]]
    __indexes__: ClassVar[tuple[list[str], bool]]

    @classmethod
    def to_db_schema(cls) -> dict[str, type[Any]]:
        """Resolve dataclass field types into SQLite-compatible storage types."""
        return {field.name: _sqlite_field_type(field.type) for field in fields(cls)}

    def to_dict(self) -> dict[str, Any]:
        """将 dataclass 转换为字典，处理 Enum 类型"""
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Enum):
                d[k] = v.value
        return d
