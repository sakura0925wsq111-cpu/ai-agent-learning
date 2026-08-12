"""Independent, offline-first career reference data subsystem."""

from .db import CareerDataDatabase
from .repository import CareerDataRepository

__all__ = ["CareerDataDatabase", "CareerDataRepository"]
