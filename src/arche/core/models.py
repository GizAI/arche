"""Base model classes with automatic serialization.

Eliminates 20+ individual to_dict() implementations across the codebase.
"""

from dataclasses import dataclass, field, fields, asdict
from datetime import datetime
from enum import Enum
from typing import TypeVar, Any, get_type_hints, get_origin, get_args

T = TypeVar("T")


def _serialize_value(value: Any) -> Any:
    """Serialize a value for JSON output."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, DataModel):
        return value.to_dict()
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


def _deserialize_value(value: Any, field_type: type) -> Any:
    """Deserialize a value from JSON input."""
    if value is None:
        return None

    # Handle Optional types
    origin = get_origin(field_type)
    if origin is type(None) or value is None:
        return value

    # Union types (e.g., str | None)
    if origin is type(None):
        return value

    # Handle datetime
    if field_type is datetime or (hasattr(field_type, "__origin__") and datetime in get_args(field_type)):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    # Handle Enums
    if isinstance(field_type, type) and issubclass(field_type, Enum):
        return field_type(value)

    # Handle DataModel subclasses
    if isinstance(field_type, type) and issubclass(field_type, DataModel):
        if isinstance(value, dict):
            return field_type.from_dict(value)
        return value

    # Handle list types
    if origin is list:
        args = get_args(field_type)
        if args:
            item_type = args[0]
            return [_deserialize_value(v, item_type) for v in value]
        return value

    return value


@dataclass
class DataModel:
    """Base class for all data models.

    Provides automatic to_dict() and from_dict() serialization,
    eliminating boilerplate across all dataclasses.

    Example:
        @dataclass
        class TodoItem(DataModel):
            id: str
            content: str
            status: str

        todo = TodoItem(id="1", content="Test", status="pending")
        data = todo.to_dict()  # Automatic serialization
        todo2 = TodoItem.from_dict(data)  # Automatic deserialization
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization.

        Handles:
        - datetime -> ISO format string
        - Enum -> value
        - Nested DataModel -> recursive to_dict()
        - List of DataModel -> list of dicts
        """
        result = {}
        for f in fields(self):
            # Skip private fields (start with _)
            if f.name.startswith("_"):
                continue
            value = getattr(self, f.name)
            result[f.name] = _serialize_value(value)
        return result

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """Create instance from dictionary.

        Handles:
        - ISO format string -> datetime
        - Enum value -> Enum
        - Nested dict -> DataModel
        """
        if not data:
            raise ValueError("Cannot create from empty dict")

        # Get field info
        field_types = {}
        try:
            field_types = get_type_hints(cls)
        except Exception:
            # Fallback to field.type if get_type_hints fails
            for f in fields(cls):
                field_types[f.name] = f.type

        # Build kwargs, skipping unknown fields and private fields
        kwargs = {}
        for f in fields(cls):
            if f.name.startswith("_"):
                continue
            if f.name in data:
                field_type = field_types.get(f.name, type(data[f.name]))
                kwargs[f.name] = _deserialize_value(data[f.name], field_type)

        return cls(**kwargs)


@dataclass
class TimestampedModel(DataModel):
    """DataModel with automatic timestamp tracking.

    Adds created_at (auto-set on creation) and updated_at fields.
    """
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now()
