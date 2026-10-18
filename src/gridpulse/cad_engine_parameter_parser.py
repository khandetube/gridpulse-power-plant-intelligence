"""Explicit advanced engineering parameter extraction.

Only unambiguous numeric expressions are accepted. This parser never infers a
code limit, equipment rating or missing physical property.
"""
from __future__ import annotations

import re


def parse_advanced_parameters(prompt: str) -> dict[str, float]:
    text = prompt.replace(",", "")
    patterns = {
        "max_velocity_m_s": r"(?:max(?:imum)?|allowable|مجاز)\s*(?:velocity|سرعت)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*m/s",
        "pump_head_m": r"(?:pump\s*)?(?:head|هد)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*m\b",
        "pump_efficiency": r"(?:pump\s*)?(?:efficiency|راندمان\s*پمپ)\s*(?:=|:)?\s*(0?\.[0-9]+|1(?:\.0)?)",
        "cable_reactance_ohm_km": r"(?:cable\s*)?(?:reactance|راکتانس)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:ohm/km|Ω/km|ohm\/km)",
        "resistance_temperature_factor": r"(?:resistance\s*)?(?:temperature\s*factor|ضریب\s*دمای\s*مقاومت)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)",
        "transformer_mva": r"(?:transformer|ترانس(?:فورمر)?)\s*([0-9]+(?:\.[0-9]+)?)\s*MVA",
        "transformer_voltage_kv": r"(?:transformer|ترانس(?:فورمر)?)\s*(?:voltage|ولتاژ)\s*([0-9]+(?:\.[0-9]+)?)\s*kV",
        "transformer_impedance_pct": r"(?:transformer|ترانس(?:فورمر)?)\s*(?:impedance|امپدانس|Z)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        "cable_count": r"(?:cable|کابل)\s*(?:count|تعداد)\s*([0-9]+)",
        "cable_outer_diameter_mm": r"(?:cable|کابل)\s*(?:outer\s*diameter|قطر\s*خارجی)\s*([0-9]+(?:\.[0-9]+)?)\s*mm",
        "max_voltage_drop_pct": r"(?:max(?:imum)?|allowable|مجاز)\s*(?:voltage\s*drop|افت\s*ولتاژ)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        "max_tray_fill_pct": r"(?:max(?:imum)?|allowable|مجاز)\s*(?:tray\s*fill|پرشدگی\s*سینی)\s*(?:=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        "conductor_resistivity_ohm_m": r"(?:resistivity|مقاومت\s*ویژه)\s*([0-9]+(?:\.[0-9]+)?(?:e[-+]?\d+)?)\s*(?:ohm\.?m|Ω\.m)",
    }
    result: dict[str, float] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        try:
            result[key] = float(match.group(1))
        except ValueError:
            continue
    return result
