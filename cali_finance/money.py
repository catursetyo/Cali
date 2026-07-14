from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def parse_amount(raw: str | int, *, allow_zero: bool = False) -> int:
    if isinstance(raw, int):
        amount = raw
    else:
        value = normalize(str(raw)).replace("rp", "").replace(" ", "")
        multiplier = Decimal(1)
        suffixes = {
            "juta": Decimal(1_000_000),
            "jt": Decimal(1_000_000),
            "ribu": Decimal(1_000),
            "rb": Decimal(1_000),
            "k": Decimal(1_000),
        }
        for suffix, factor in suffixes.items():
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                multiplier = factor
                break

        if multiplier == 1:
            value = value.replace(".", "").replace(",", "")
        else:
            value = value.replace(".", "").replace(",", ".")

        try:
            amount = int(Decimal(value) * multiplier)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid amount: {raw!r}") from exc

    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("Amount must be greater than 0.")
    return amount


def parse_signed_amount(raw: str | int) -> int:
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    return sign * parse_amount(text, allow_zero=True)


def rupiah(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return sign + "Rp" + f"{abs(int(amount)):,}".replace(",", ".")


def percent(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")
