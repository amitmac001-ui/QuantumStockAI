from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ServiceResult:

    success: bool
    data: Any = None
    message: str = ""
    errors: Any = None

    @classmethod
    def ok(cls, data=None, message="Success"):
        return cls(
            success=True,
            data=data,
            message=message,
        )

    @classmethod
    def fail(cls, message="Failed", errors=None):
        return cls(
            success=False,
            message=message,
            errors=errors,
        )
