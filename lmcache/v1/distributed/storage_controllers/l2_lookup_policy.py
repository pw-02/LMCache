# SPDX-License-Identifier: Apache-2.0
"""Policies that decide whether a request may consult remote L2 storage.

The decision is intentionally made before the prefetch controller starts its
L2 lookup.  Skipping L2 still allows keys already resident in local L1 to be
used; only missing keys are left for the serving engine to recompute.
"""

# Future
from __future__ import annotations

# Standard
from dataclasses import dataclass
from typing import Literal


L2LookupPolicyName = Literal["always", "never", "min_tokens"]
L2_LOOKUP_POLICY_NAMES: tuple[L2LookupPolicyName, ...] = (
    "always",
    "never",
    "min_tokens",
)


@dataclass(frozen=True)
class L2LookupDecisionPolicy:
    """Static request-size policy for remote L2 lookups.

    Args:
        name: ``always`` consults L2 for every L1 miss, ``never`` always
            recomputes misses, and ``min_tokens`` consults L2 only when the
            chunk-aligned requested prefix is at least ``min_tokens``.
        min_tokens: Threshold used by ``min_tokens``. It must be positive for
            that mode and is ignored by the other modes.
    """

    name: L2LookupPolicyName = "always"
    min_tokens: int = 0

    def __post_init__(self) -> None:
        if self.name not in L2_LOOKUP_POLICY_NAMES:
            raise ValueError(
                f"Unknown L2 lookup policy {self.name!r}; expected one of "
                f"{', '.join(L2_LOOKUP_POLICY_NAMES)}"
            )
        if self.min_tokens < 0:
            raise ValueError("L2 lookup minimum tokens cannot be negative")
        if self.name == "min_tokens" and self.min_tokens <= 0:
            raise ValueError(
                "L2 lookup minimum tokens must be positive when policy is "
                "'min_tokens'"
            )

    def should_lookup_l2(self, requested_tokens: int) -> bool:
        """Return whether L2 may be consulted for this request."""
        if requested_tokens < 0:
            raise ValueError("Requested token count cannot be negative")
        if self.name == "always":
            return True
        if self.name == "never":
            return False
        return requested_tokens >= self.min_tokens

