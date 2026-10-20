"""Unit-aware numeric conversions for engineering analytics using Pint."""
from __future__ import annotations

import math

from pint import UnitRegistry
from pint.errors import DimensionalityError, UndefinedUnitError

_UREG = UnitRegistry(autoconvert_offset_to_baseunit=True)


def convert_value(value: float, from_unit: str, to_unit: str) -> dict[str, object]:
    """Convert a finite scalar between compatible Pint units."""
    if not math.isfinite(value):
        raise ValueError("value must be finite")
    if not from_unit.strip() or not to_unit.strip():
        raise ValueError("from_unit and to_unit must not be empty")
    try:
        source = _UREG.Quantity(value, from_unit)
        converted = source.to(to_unit)
    except UndefinedUnitError as exc:
        raise ValueError("unknown source or target unit") from exc
    except DimensionalityError as exc:
        raise ValueError("source and target units are dimensionally incompatible") from exc
    except (ValueError, TypeError) as exc:
        raise ValueError("unknown source or target unit or invalid unit expression") from exc

    result = float(converted.magnitude)
    if not math.isfinite(result):
        raise ValueError("conversion result is not finite")
    return {
        "input_value": value,
        "from_unit": from_unit,
        "converted_value": result,
        "to_unit": to_unit,
        "dimension": str(converted.dimensionality),
        "library": "Pint",
        "note": "Conversion validates unit compatibility; it does not validate the source measurement or its engineering context.",
    }
