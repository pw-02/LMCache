# System design: replacement-worker KV-cache recovery

## Objective

The deployment contains worker-local KV storage (L1), shared remote KV storage
(L2), and a MalleServe head service that remains available when a worker host is
lost. A replacement worker starts with an empty L1. The system attempts to copy
a useful subset of previous KV state into that L1 without requiring a complete
inventory or synchronization of L2.

The current fault model assumes that the head service and L2 survive worker-host
loss. Head restart, L2 replication, conversion between incompatible KV layouts,
and adaptive replica placement are outside the implementation.

## The three decisions

The design separates three questions:

1. **Request-time retrieval:** may an L1 miss read from L2, or should the serving
   engine recompute it?
2. **Persistence:** should newly computed KV be written from L1 to L2?
3. **Replacement recovery:** which previously observed prefixes should be copied
   from L2 into a replacement L1 before the worker becomes routable?

Keeping these decisions independent permits controlled experiments. For example,
L2 persistence can be reduced without disabling L1 storage, and two recovery
policies can be compared using identical request-time fallback behaviour.

## Prefix history

During real lookups, LMCache records several complete, chunk-aligned prefixes.
It keeps power-of-two prefix lengths plus the final aligned prefix. Each
observation records:

- model and tensor-parallel world size;
- cache namespace;
- prefix token IDs;
- chunk size and logical KV size;
- number of observations;
- time of the latest observation.

The cache namespace is the recovery-facing name for LMCache's internal
``cache_salt`` field. It prevents observations from different cache domains or
tenants from being merged.

The implementation has fixed entry, token and per-key-hint limits. These limits
are safety properties of the implementation, not part of the name of the data
structure or the recovery policy.

An observation says that a prefix was requested. It does not guarantee that the
KV object remains in L2. Remote eviction is detected naturally when a recovery
load returns fewer keys than requested.

## Preserving history after worker loss

The worker supervisor periodically reads ``GET /cache/prefix-history`` and sends
the snapshot to ``POST /recovery/history`` on the MalleServe head service. The
head service validates entries and retains recent observations from each host.
Empty snapshots produced by a newly started host do not immediately erase the
older history.

This history remains available when the worker host disappears, provided that
the head service continues running. It is currently held in head-process memory
and is not durable across a head restart.

## Recovery policies

The public configuration uses one policy field:

| Policy | Selection rule |
|---|---|
| ``off`` | Do not perform pre-admission transfers |
| ``longest_first`` | Prefer longer observed prefixes |
| ``reuse_priority`` | Prefer recent and repeatedly observed prefixes per byte |
| ``benefit_priority`` | Prefer positive estimated recomputation saving per byte |

For observation (e), ``reuse_priority`` uses

\[
R(e)=\frac{n_e 2^{-a_e/h}t_e}{b_e},
\]

where (n_e) is the observation count, (a_e) is age, (h) is the recency
half-life, (t_e) is the number of prefix tokens and (b_e) is logical KV size.

``benefit_priority`` estimates

\[
T_{remote}(e)=\delta + b_e/\hat r
\]

and scores

\[
B(e)=\frac{n_e 2^{-a_e/h}
\max(\gamma t_e-T_{remote}(e),0)}{b_e}.
\]

The recomputation coefficient \(\gamma\) is measured separately. The effective
transfer rate \(\hat r\) is updated from completed loads using an EWMA. It
includes queueing, polling and deserialization rather than representing only
physical network bandwidth.

## Recovery limits

The transfer allowance is

\[
A=\min(A_{max}, fC_{L1}, \max(C_{L1}-U_{L1},0)),
\]

where (A_{max}) is the configured absolute transfer limit, (f) is the
configured maximum L1 fraction, (C_{L1}) is L1 capacity and (U_{L1}) is
observed usage. The attempt also has time, prefix-count, prefix-length and age
limits.

Only one complete prefix is submitted at a time. This simplifies accounting and
limits an expired attempt to at most one outstanding backend request. A time
limit stops waiting and issuing further work; it cannot cancel Redis I/O already
accepted by LMCache.

## Overlap with vLLM initialization

The LMCache process can start before vLLM, but it cannot deserialize model KV
objects until vLLM's connector registers the actual layout. Layout registration
occurs after vLLM allocates its KV tensors and before the worker necessarily
passes an inference-readiness probe.

MalleServe therefore starts a recovery task immediately after launching vLLM.
The task polls the local prefix-history endpoint until the layout appears, then
starts L2-to-L1 transfers while vLLM continues initialization. When vLLM becomes
inference-ready, the controller waits for any unfinished part of the recovery
attempt and only then starts its routing heartbeat.

This ordering can hide transfer time behind model initialization without
guessing the layout or routing requests during recovery. An experiment setting
can disable overlap and reproduce the previous post-readiness ordering.

## Concurrency and fallback

The head service grants one recovery lease at a time to reduce simultaneous
Redis bursts. Workers sharing a host also share one L1, so same-layout readiness
events wait for a host-level attempt and can reuse its recent result.

Recovery is fail-open for worker availability. Missing history, missing L2
objects, a denied lease, an unsupported layout, a timeout or an HTTP error ends
the attempt and allows the worker to use its configured lazy-L2 or recomputation
fallback. A generation check prevents a worker preempted during recovery from
starting a stale heartbeat.

## Persistence admission

Persistence admission is evaluated after an L1 write completes and before the
store controller submits L2 writes. Its values are ``always``, ``never`` and
``min_tokens``. The token threshold uses a per-key hint containing the largest
aligned request length that observed that key; it does not use asynchronous
batch size. Rejected persistence leaves the L1 object available.

Objects loaded from L2 notify L1 eviction bookkeeping through a separate event
path and are not immediately persisted back to L2.

## Evaluation requirements

Restarting vLLM alone is not a replacement-worker recovery experiment because
the host LMCache L1 survives. A valid experiment must restart LMCache or use a
new host while keeping the head service and L2 alive.

Comparisons should keep workload, L2 contents, history, hardware and transfer
limits constant. Report worker admission time, first-request TTFT, time to
steady state, recomputed tokens, cache hits, actual network traffic, surviving
worker interference and the measured startup-overlap interval.

The current token-addressed path supports one full-attention object group.
Sliding-window, MLA, pipeline-parallel and disaggregated layouts require
separate validation.
