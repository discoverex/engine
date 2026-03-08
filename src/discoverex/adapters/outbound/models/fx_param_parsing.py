from __future__ import annotations


def as_positive_int(value: object, *, fallback: int) -> int:
    if value is None:
        return fallback
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, (int, float, str)):
        parsed = int(value)
    else:
        raise ValueError("expected int-compatible value")
    if parsed < 1:
        raise ValueError("expected positive integer")
    return parsed


def as_int_or_none(value: object, *, fallback: int | None) -> int | None:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError("expected int-compatible value")


def as_float(value: object, *, fallback: float) -> float:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError("expected float-compatible value")


def as_str(value: object, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback
