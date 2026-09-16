"""Global test isolation for process-local safety fallbacks."""

import pytest

from core.ai_quota import reset_ai_quota_manager
from core.rate_limit import reset_rate_limit_state


@pytest.fixture(autouse=True)
def reset_safety_limiters():
    reset_rate_limit_state()
    reset_ai_quota_manager()
    yield
    reset_rate_limit_state()
    reset_ai_quota_manager()
