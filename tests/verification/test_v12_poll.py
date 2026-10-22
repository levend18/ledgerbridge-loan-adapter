from tests.integration.test_poll import (
    test_v12_automatic_poll_and_v13_no_duplicate_work,
    test_v14_patch_is_published_by_poll,
)
import pytest

pytestmark = pytest.mark.live_worker
__all__ = [
    "test_v12_automatic_poll_and_v13_no_duplicate_work",
    "test_v14_patch_is_published_by_poll",
]
