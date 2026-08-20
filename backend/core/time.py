"""Application time helpers for user-facing date semantics."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def business_now() -> datetime:
    """Return the current application time in the product timezone."""

    return datetime.now(BUSINESS_TIMEZONE)


def business_today() -> date:
    """Return the product's canonical current date."""

    return business_now().date()
