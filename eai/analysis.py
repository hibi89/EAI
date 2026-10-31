"""Independent bounded CPU numeric comparison of user-provided observations.

This is a deterministic solver, not an LLM response generator. It never fetches
external data, infers units or silently treats label order as chronological.
"""
from decimal import Decimal, localcontext
import re

# IntentSpec v1 query limit is 2_000; numeric solver deliberately has tighter caps.
_MAX_ITEMS = 16
_MAX_INPUT = 500
_NAME = re.compile(r"^[^,;=\n\r\t]{1,32}$")
_NUMBER = re.compile(r"^[+-]?(?:\d{1,24}(?:\.\d{1,12})?|\.\d{1,12})$")


def _render_decimal(value: Decimal) -> str:
    """Stable decimal display, retaining exact fixed-point values."""
    out = format(value, "f")
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return "0" if out in {"-0", "", "+0"} else out


def compare_numeric_observations(payload: str) -> dict:
    """Rank numeric observations and show input-order changes where meaningful.

    Grammar: label=decimal,label=decimal (commas/semicolons are separators).
    Percent change is only defined when the previous observation is positive.
    This intentionally does not extrapolate a trend or assume period semantics.
    """
    if not isinstance(payload, str) or not 1 <= len(payload.strip()) <= _MAX_INPUT:
        raise ValueError("비교 데이터는 1~500자여야 합니다.")
    parts = re.split(r"[,;]", payload)
    if not 2 <= len(parts) <= _MAX_ITEMS:
        raise ValueError("비교 항목은 2~16개여야 합니다.")
    observations = []
    unique = set()
    for part in parts:
        if part.count("=") != 1:
            raise ValueError("입력 형식: 비교 A=100,B=120")
        name, value = (section.strip() for section in part.split("=", 1))
        if not _NAME.fullmatch(name) or not name.strip():
            raise ValueError("항목 이름이 올바르지 않습니다.")
        if name.casefold() in unique:
            raise ValueError("항목 이름이 중복됩니다.")
        unique.add(name.casefold())
        if not _NUMBER.fullmatch(value):
            raise ValueError("숫자는 부호와 소수점을 포함한 유한 십진수여야 합니다.")
        observations.append((name, Decimal(value)))

    with localcontext() as ctx:
        ctx.prec = 90
        ranked = sorted(observations, key=lambda item: item[1], reverse=True)
        report = {
            "rows": [{"name": name, "value": _render_decimal(val)} for name, val in observations],
            "ranked": [{"name": name, "value": _render_decimal(val)} for name, val in ranked],
            "max": {"name": ranked[0][0], "value": _render_decimal(ranked[0][1])},
            "min": {"name": ranked[-1][0], "value": _render_decimal(ranked[-1][1])},
            "gap": _render_decimal(ranked[0][1] - ranked[-1][1]),
            "changes": [],
            "notes": ["사용자 제공 숫자만 사용했습니다. 단위와 기간은 검증하지 않았습니다."],
        }
        for ((prev_name, prev), (name, current)) in zip(observations, observations[1:]):
            diff = current - prev
            change = {"from": prev_name, "to": name, "absolute": _render_decimal(diff), "percent": None}
            if prev > 0:
                pct = (diff / prev) * Decimal(100)
                change["percent"] = _render_decimal(pct.quantize(Decimal("0.01")))
            report["changes"].append(change)
        if any(change["percent"] is None for change in report["changes"]):
            report["notes"].append("직전 값이 0 이하인 구간은 일반적인 증감률(%)을 표시하지 않았습니다.")
        return report
