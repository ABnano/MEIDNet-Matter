# engine/ — the MEIDNet engine, vendored

`meidnet/` is a snapshot of the MEIDNet package at the research checkout recorded in `SNAPSHOT.json`
(upstream commit 26a0387862 plus the uncommitted work of the staged-evaluation rounds), and `meidnet_eval/` holds the
evaluation components (the ten blocks and their bands in `stages.py`, the generation, judging, relaxation and
calibration scripts).  Install with `pip install ./engine` **before** `pip install -e .`; the distribution is named
`meidnet` (2.4.0.dev2) so the application's `meidnet>=2.2.0,<3` dependency resolves to it and nothing is fetched from PyPI.

On PyPI, `meidnet` 2.4.0.dev2 is this snapshot, uploaded by MEIDNet-Matter's release workflow so that `pip install meidnet-matter`
resolves without a clone; the upstream MEIDNet release 2.4.0 (https://github.com/ABnano/MEIDNet) will replace it.

Snapshot taken 2026-10-08.  To refresh it: `python scripts/vendor_engine.py --src <checkout>`.  The upstream release of this
work is planned as meidnet 2.4.0; when it exists, this folder is removed and the dependency pinned to that release.
