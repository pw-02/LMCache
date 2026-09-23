# SPDX-License-Identifier: Apache-2.0
"""Recent request-prefix observations used for cache recovery.

The history describes what was requested.  It is deliberately not an inventory
of objects currently stored in L2: remote entries may be evicted after an
observation is recorded, and recovery handles that as a normal partial result.
"""

# Standard
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Hashable
import hashlib
import json
import threading
import time


@dataclass
class PrefixObservation:
    """One complete, chunk-aligned prefix observed during a real lookup."""

    identity: str
    model_name: str
    world_size: int
    cache_namespace: str
    token_ids: list[int]
    chunk_size: int
    size_bytes: int
    observation_count: int
    last_observed_at: float


class PrefixHistory:
    """Remember recent prefixes and per-key request lengths with fixed limits.

    ``history_entries`` limits the number of prefix observations.  Setting it
    to zero disables token retention while preserving the small per-key length
    hints used by L2 persistence admission.
    """

    def __init__(
        self,
        history_entries: int = 0,
        token_limit: int = 1_048_576,
        key_hint_limit: int = 65_536,
    ) -> None:
        if history_entries < 0 or token_limit <= 0 or key_hint_limit <= 0:
            raise ValueError("Invalid prefix-history limits")
        self.history_entries = history_entries
        self.token_limit = token_limit
        self.key_hint_limit = key_hint_limit
        self._observations: OrderedDict[str, PrefixObservation] = OrderedDict()
        self._key_lengths: OrderedDict[Hashable, int] = OrderedDict()
        self._retained_tokens = 0
        self._lock = threading.Lock()

    def observe(
        self,
        keys: list[Hashable],
        model_name: str,
        world_size: int,
        cache_namespace: str,
        token_ids: list[int],
        chunk_size: int,
        bytes_per_chunk: int,
        track_key_lengths: bool = True,
        retain_prefixes: bool = True,
    ) -> None:
        """Record a lookup using power-of-two prefixes plus its final prefix."""
        if chunk_size <= 0 or bytes_per_chunk <= 0 or world_size <= 0:
            raise ValueError("Chunk size, byte size, and world size must be positive")
        aligned = len(token_ids) // chunk_size * chunk_size
        with self._lock:
            if track_key_lengths:
                for key in keys:
                    self._key_lengths[key] = max(
                        aligned, self._key_lengths.get(key, 0)
                    )
                    self._key_lengths.move_to_end(key)
                while len(self._key_lengths) > self.key_hint_limit:
                    self._key_lengths.popitem(last=False)

            if not retain_prefixes or not self.history_entries or not aligned:
                return

            lengths = {aligned}
            length = chunk_size
            while length < aligned:
                lengths.add(length)
                length *= 2

            now = time.time()
            for length in sorted(lengths):
                if length > self.token_limit:
                    continue
                tokens = token_ids[:length]
                identity = hashlib.sha256(
                    json.dumps(
                        [
                            model_name,
                            world_size,
                            cache_namespace,
                            chunk_size,
                            tokens,
                        ],
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                observation = self._observations.pop(identity, None)
                if observation is None:
                    observation = PrefixObservation(
                        identity=identity,
                        model_name=model_name,
                        world_size=world_size,
                        cache_namespace=cache_namespace,
                        token_ids=tokens,
                        chunk_size=chunk_size,
                        size_bytes=length // chunk_size * bytes_per_chunk,
                        observation_count=0,
                        last_observed_at=now,
                    )
                    self._retained_tokens += length
                observation.observation_count += 1
                observation.last_observed_at = now
                self._observations[identity] = observation

                while (
                    len(self._observations) > self.history_entries
                    or self._retained_tokens > self.token_limit
                ):
                    _, removed = self._observations.popitem(last=False)
                    self._retained_tokens -= len(removed.token_ids)

    def admits_persistence(self, key: Hashable, minimum_tokens: int) -> bool:
        """Whether the key was seen in a request meeting the token threshold."""
        with self._lock:
            return self._key_lengths.get(key, 0) >= minimum_tokens

    def snapshot(self) -> dict:
        """Return a detached JSON-compatible copy of the prefix history."""
        with self._lock:
            return {
                "schema_version": 2,
                "generated_at": time.time(),
                "observations": [
                    asdict(observation)
                    for observation in self._observations.values()
                ],
                "retained_tokens": self._retained_tokens,
                "history_entries": self.history_entries,
            }
