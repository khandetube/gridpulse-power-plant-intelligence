"""Explicit-unit power generation performance calculations.

These formulas are only valid when the supplied period, net/gross basis, and
energy boundaries are aligned. Outputs are engineering indicators, not control advice.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def calculate_generation_performance(
    *,
    net_generation_mwh: float,
    fuel_thermal_input_mwh: float,
    net_capacity_mw: float,
    period_hours: float,
) -> dict[str, Any]:
    """Calculate net efficiency, net heat rate, and capacity factor.

    Formulae:
      net efficiency (%) = net electrical MWh / fuel thermal MWh × 100
      net heat rate (kJ/kWh) = fuel thermal MWh / net electrical MWh × 3600
      capacity factor (%) = net electrical MWh / (net capacity MW × period h) × 100

    The thermal input must use a compatible lower/heating-value convention and
    cover the same time interval as net generation.
    """
    values = {
        "net_generation_mwh": net_generation_mwh,
        "fuel_thermal_input_mwh": fuel_thermal_input_mwh,
        "net_capacity_mw": net_capacity_mw,
        "period_hours": period_hours,
    }
    for name, value in values.items():
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")

    efficiency = net_generation_mwh / fuel_thermal_input_mwh * 100.0
    heat_rate = fuel_thermal_input_mwh / net_generation_mwh * 3600.0
    capacity_factor = net_generation_mwh / (net_capacity_mw * period_hours) * 100.0

    warnings: list[str] = []
    if efficiency > 100:
        warnings.append(
            "Calculated net efficiency exceeds 100%; check energy boundaries, units, "
            "period alignment, and fuel heating-value convention."
        )
    if capacity_factor > 100:
        warnings.append(
            "Calculated capacity factor exceeds 100%; check net capacity basis, "
            "generation units, and period duration."
        )

    return {
        "net_efficiency_percent": efficiency,
        "net_heat_rate_kj_per_kwh": heat_rate,
        "capacity_factor_percent": capacity_factor,
        "inputs": values,
        "formula_version": "gridpulse-generation-performance-v1",
        "warnings": warnings,
        "assumptions": [
            "Net electrical generation and net capacity use the same plant/unit boundary.",
            "Fuel thermal input and electrical output cover the same reporting interval.",
            "Fuel input is expressed as thermal MWh using a documented heating-value basis.",
            "No adjustment is made for ambient conditions, startup/shutdown, auxiliary loads, or fuel quality.",
        ],
        "not_a_diagnosis": (
            "Results are calculated indicators. They are not independently verified "
            "and should not be used alone to diagnose faults or direct plant operation."
        ),
    }
