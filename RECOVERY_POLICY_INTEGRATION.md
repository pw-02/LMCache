# Recovery-policy branch integration

This source tree is based directly on:

- repository: `https://github.com/pw-02/LMCache.git`
- branch: `recovery-policy`
- base commit: `ce5863faf4d035d4d0ce5b40ab403b68eeec7981`

The recovery extension was applied and tested against that exact revision. No
changes from another LMCache release were merged into this tree.

## What this adds

- independent admission rules for retrieving from and persisting to L2;
- prefix-history recording from real cache lookups;
- a read-only `GET /cache/prefix-history` endpoint;
- warm prefetch into the worker's L1 cache;
- recovery-facing `cache_namespace` naming while retaining LMCache's existing
  internal `cache_salt` field;
- configuration, documentation, and focused recovery tests.

## Using this tree

The simplest integration is to use this directory as the LMCache source tree:

```bash
pip install -e .
```

An accompanying patch is also provided for an unchanged checkout of the same
branch. Verify it before applying:

```bash
git switch recovery-policy
git rev-parse HEAD
git apply --check lmcache-recovery-policy-integrated.patch
git apply lmcache-recovery-policy-integrated.patch
```

The reported revision must be
`ce5863faf4d035d4d0ce5b40ab403b68eeec7981`. If your checkout contains local
changes, commit or stash them before applying the patch.

The relevant user documentation is in:

- `docs/source/developer_guide/recovery_policy.rst`
- `docs/design/v1/distributed/recovery.md`

## Focused validation

The CPU-only prefix-history tests can run without the LMCache native extension:

```bash
python -m unittest tests.recovery_unit.test_prefix_history -v
```

In a normal LMCache development environment, also run:

```bash
python -m pytest -q \
  tests/v1/distributed/test_persistence_admission.py \
  tests/v1/distributed/test_prefetch_controller.py \
  tests/v1/multiprocess/test_warm_prefetch.py \
  tests/v1/multiprocess/http_apis/test_cache_api.py
```

For a valid recovery experiment, restart LMCache or use a replacement host so
that L1 is genuinely cold. Restarting only vLLM can preserve the LMCache L1 and
does not measure cache reconstruction.
