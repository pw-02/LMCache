# SPDX-License-Identifier: Apache-2.0
"""CPU-only prefix-history tests; runnable without native extensions."""

# Standard
import unittest

# First Party
from lmcache.v1.distributed.prefix_history import PrefixHistory


class PrefixHistoryTests(unittest.TestCase):
    def observe(
        self,
        history: PrefixHistory,
        n: int = 1024,
        salt: str = "",
        retain: bool = True,
    ) -> None:
        history.observe(
            ["first", "second"],
            "model",
            1,
            salt,
            list(range(n)),
            256,
            1024,
            retain_prefixes=retain,
        )

    def test_prefixes_are_aligned_with_correct_bytes(self) -> None:
        history = PrefixHistory(history_entries=16)
        self.observe(history, 1025)
        records = history.snapshot()["observations"]
        self.assertEqual([len(e["token_ids"]) for e in records], [256, 512, 1024])
        self.assertEqual([e["size_bytes"] for e in records], [1024, 2048, 4096])

    def test_shared_prefix_frequency_and_tenant_isolation(self) -> None:
        history = PrefixHistory(history_entries=16)
        self.observe(history)
        self.observe(history)
        self.observe(history, salt="another-tenant")
        records = history.snapshot()["observations"]
        self.assertEqual(len(records), 6)
        self.assertEqual([e["observation_count"] for e in records[:3]], [2, 2, 2])
        self.assertEqual([e["observation_count"] for e in records[3:]], [1, 1, 1])

    def test_bounds_and_detached_snapshot(self) -> None:
        history = PrefixHistory(history_entries=2, token_limit=1024, key_hint_limit=1)
        self.observe(history)
        result = history.snapshot()
        self.assertLessEqual(len(result["observations"]), 2)
        self.assertLessEqual(result["retained_tokens"], 1024)
        result["observations"][0]["token_ids"][0] = 99
        self.assertEqual(history.snapshot()["observations"][0]["token_ids"][0], 0)
        self.assertFalse(history.admits_persistence("first", 1))
        self.assertTrue(history.admits_persistence("second", 1024))
        self.assertFalse(history.admits_persistence("second", 1025))

    def test_disabled_history_still_tracks_admission_without_tokens(self) -> None:
        history = PrefixHistory()
        self.observe(history)
        self.assertFalse(history.snapshot()["observations"])
        self.assertTrue(history.admits_persistence("first", 1024))
        self.assertFalse(history.admits_persistence("unknown", 1))

    def test_unsupported_layout_keeps_only_admission_hints(self) -> None:
        history = PrefixHistory(history_entries=16)
        self.observe(history, retain=False)
        self.assertFalse(history.snapshot()["observations"])
        self.assertTrue(history.admits_persistence("first", 1024))


if __name__ == "__main__":
    unittest.main()
