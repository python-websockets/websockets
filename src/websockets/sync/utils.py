from __future__ import annotations

import time
from typing import Optional


__all__ = ["Deadline"]


class Deadline:
    """
    Manage timeouts across multiple steps.

    Args:
        timeout: time available in seconds; :obj:`None` if there is no limit.

    """

    def __init__(self, timeout: Optional[float]) -> None:
        self.deadline: Optional[float]
        if timeout is None:
            self.deadline = None
        else:
            self.deadline = time.monotonic() + timeout

    def timeout(self) -> Optional[float]:
        """
        Calculate a timeout from a deadline.

        Returns:
            Optional[float]: Time left in seconds; :obj:`None` if there is no limit.

        """
        if self.deadline is None:
            return None
        else:
            return self.deadline - time.monotonic()
