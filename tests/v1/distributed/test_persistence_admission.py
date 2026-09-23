# SPDX-License-Identifier: Apache-2.0
"""Persistence admission uses lookup metadata without changing L1 retention."""

# Third Party
import pytest

# First Party
from lmcache.v1.distributed.prefix_history import PrefixHistory
from lmcache.v1.distributed.storage_controllers.store_policy import (
    AdapterDescriptor,
    AdmissionStorePolicy,
    DefaultStorePolicy,
)


def test_never_persistence_does_not_route_or_delete() -> None:
    policy = AdmissionStorePolicy(DefaultStorePolicy(), PrefixHistory(), "never")
    assert policy.select_store_targets(["key"], [AdapterDescriptor(0, None)]) == {0: []}
    assert policy.select_l1_deletions([]) == []
    assert policy.statistics()["skipped_keys"] == 1


def test_threshold_routes_whole_observed_prefix_inclusively() -> None:
    history = PrefixHistory()
    history.observe(
        ["first", "last"], "model", 1, "", list(range(4096)), 256, 1024
    )
    policy = AdmissionStorePolicy(DefaultStorePolicy(), history, "min_tokens", 4096)
    assert policy.select_store_targets(
        ["first", "last", "unknown"], [AdapterDescriptor(0, None)]
    ) == {0: ["first", "last"]}
    assert policy.select_l1_deletions(["first", "last"]) == []


def test_invalid_minimum_rejected() -> None:
    with pytest.raises(ValueError):
        AdmissionStorePolicy(DefaultStorePolicy(), PrefixHistory(), "min_tokens", 0)
