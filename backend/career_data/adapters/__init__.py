"""Isolated source adapters."""

from .civil_service import CivilServiceAdapter
from .postgraduate import PostgraduateAdapter
from .qut_transfer import QutTransferAdapter
from .salary import SalaryAdapter
from .shandong_civil_service import ShandongCivilServiceAdapter
from .undergraduate import UndergraduateMajorsAdapter

ADAPTERS = {
    "postgraduate": PostgraduateAdapter,
    "undergraduate-majors": UndergraduateMajorsAdapter,
    "salary": SalaryAdapter,
    "civil-service": CivilServiceAdapter,
    "shandong-civil-service": ShandongCivilServiceAdapter,
    "qut-transfer": QutTransferAdapter,
}

__all__ = ["ADAPTERS"]
