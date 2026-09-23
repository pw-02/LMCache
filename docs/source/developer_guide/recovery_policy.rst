Persistence admission and prefix-history recovery
=================================================

This MP-server extension adds two independent mechanisms:

* L2 persistence admission decides whether a completed L1 write should also be
  written to remote storage.
* Prefix history records recently observed prompt prefixes for use by an
  external replacement-worker recovery service.

Configuration
-------------

The existing ``--l2-lookup-policy`` and ``--l2-lookup-min-tokens`` options keep
their existing request-time semantics. New options are:

.. list-table::
   :header-rows: 1
   :widths: 32 15 53

   * - Option
     - Default
     - Meaning
   * - ``--l2-store-admission``
     - ``always``
     - ``always``, ``never``, or ``min_tokens``; independent of retrieval.
   * - ``--l2-store-min-tokens``
     - ``0``
     - Inclusive aligned request-token threshold for persistence.
   * - ``--prefix-history-entries``
     - ``0``
     - Number of recent prefix observations retained; zero disables token
       retention.

For example::

   --l2-store-admission min_tokens --l2-store-min-tokens 4096 \
   --prefix-history-entries 1024 --l2-prefetch-policy retain

Rejecting persistence leaves the L1 object available. The threshold is based on
the aligned request length that observed each key, not the size of an individual
chunk or asynchronous store batch. Missing length information is rejected under
``min_tokens``. Existing L1 objects are not proactively copied to L2 when a later
lookup qualifies.

Prefix-history endpoint
-----------------------

``GET /cache/prefix-history`` returns recent prefix observations, current L1
occupancy, and persistence-decision counts. Optional ``model_name`` and
``world_size`` parameters also return the registered layout and whether it
supports token-addressed recovery.

Each observation and prefetch request contains a ``cache_namespace`` field. It
maps to LMCache's established internal ``cache_salt`` identifier, which keeps
otherwise identical entries separate. Token IDs and namespaces are sensitive
deployment metadata; keep this endpoint on a trusted network.

An observation records demand, not confirmed L2 residence. LMCache retains
power-of-two aligned prefixes plus the final aligned prompt prefix. Prefix count
and retained token count have fixed limits. Multi-group and sliding-window
layouts are excluded from token-addressed recovery.

Recovery transfers
------------------

``POST /cache/prefetches`` and its status endpoint load a supplied token prefix
from L2 into retained L1 objects. Completed status includes
``already_l1_keys`` alongside ``found_keys`` and ``total_keys`` so a caller can
distinguish local hits from remote loads.

L2-origin writes update L1 eviction bookkeeping without causing redundant L2
persistence. At most 1024 warm jobs are tracked, and abandoned completed jobs
are removed after 330 seconds. An issued backend operation cannot be forcibly
cancelled by an external admission deadline.

MalleServe stores copies of the prefix history at its head service, chooses a
recovery policy, applies time/capacity/transfer limits, and controls when a
replacement worker becomes routable. Its policies are ``off``,
``longest_first``, ``reuse_priority``, and ``benefit_priority``. Normal
request-time L2 lookup remains a separate LMCache choice.

Validation
----------

The CPU-only prefix-history tests run without native extensions::

   PYTHONPATH=. python -m unittest discover -s tests/recovery_unit -v

Store, prefetch-controller, HTTP, and vLLM integration tests require the normal
LMCache native serving environment. Implementation alone does not establish a
performance improvement; a valid recovery experiment must replace or restart
host LMCache so the returning L1 is empty.
