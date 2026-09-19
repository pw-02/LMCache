# Remote L2 lookup admission policy

This change adds a request-level gate before LMCache contacts a remote L2
adapter such as Redis. It is intended for experiments that compare the cost of
remote KV retrieval with local KV recomputation.

The gate does not disable LMCache L1. A request may still reuse chunks already
resident in the local LMCache CPU tier. When the gate skips L2, any missing KV
chunks are reported as cache misses and the serving engine recomputes them.

## Configuration

The cache-server CLI accepts two new options:

```text
--l2-lookup-policy {always,never,min_tokens}
--l2-lookup-min-tokens INTEGER
```

- `always` preserves the existing behavior and is the default.
- `never` skips remote L2 for every request.
- `min_tokens` uses remote L2 only when the chunk-aligned requested prefix is
  at least `--l2-lookup-min-tokens` tokens. The boundary is inclusive.

For a runner that converts a YAML cache configuration into CLI arguments, the
equivalent configuration is:

```yaml
l2_lookup_policy: min_tokens
l2_lookup_min_tokens: 8192
```

The token count is chunk-aligned because trailing partial chunks cannot be
looked up by LMCache. This first policy uses total lookup-eligible request
tokens, not the number of L1 misses discovered later in the lookup pipeline.

## Metrics

Two Prometheus-compatible counters expose policy behavior. Both carry a
`decision` label whose value is `use_l2` or `skip_l2`:

- `lmcache_mp_l2_lookup_policy_decisions_total`: number of requests.
- `lmcache_mp_l2_lookup_policy_tokens_total`: chunk-aligned request tokens.

Together with L2 read bytes, lookup hit tokens, TTFT, and prefill time, these
counters show whether the policy avoided remote work and whether that decision
improved end-to-end performance.

## Suggested crossover experiment

For each prefix length, run the same cold-L1 workload with:

1. `always`, representing remote Redis retrieval;
2. `never`, representing local recomputation;
3. `min_tokens` at candidate crossover thresholds.

Keep model, request order, output length, concurrency, Redis placement, and
network conditions fixed. Repeat each point so that a one-off Redis or GPU
startup effect is not mistaken for the crossover.
