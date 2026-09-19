# SPDX-License-Identifier: Apache-2.0

# Third Party
import pytest

# First Party
from lmcache.v1.distributed.storage_controllers.l2_lookup_policy import (
    L2LookupDecisionPolicy,
)


@pytest.mark.parametrize("tokens", [0, 256, 8192])
def test_always_policy_uses_l2(tokens: int) -> None:
    assert L2LookupDecisionPolicy("always").should_lookup_l2(tokens)


@pytest.mark.parametrize("tokens", [0, 256, 8192])
def test_never_policy_skips_l2(tokens: int) -> None:
    assert not L2LookupDecisionPolicy("never").should_lookup_l2(tokens)


def test_min_tokens_policy_has_inclusive_boundary() -> None:
    policy = L2LookupDecisionPolicy("min_tokens", min_tokens=2048)
    assert not policy.should_lookup_l2(1792)
    assert policy.should_lookup_l2(2048)
    assert policy.should_lookup_l2(8192)


@pytest.mark.parametrize(
    ("name", "min_tokens"),
    [("unknown", 0), ("min_tokens", 0), ("min_tokens", -1)],
)
def test_invalid_policy_configuration_is_rejected(
    name: str, min_tokens: int
) -> None:
    with pytest.raises(ValueError):
        L2LookupDecisionPolicy(name, min_tokens)  # type: ignore[arg-type]
