# Test snapshot policy

The production `contracts/`, `configs/`, and `schemas/` trees are authoritative.
Files mirrored below `tests/<area>/` are generated compatibility snapshots for
legacy isolated harnesses; they are not independently editable sources.

Regenerate them with:

```bash
python tools/sync_p7_test_snapshots.py
```

`SNAPSHOT_MANIFEST.json` records every canonical source and SHA-256. The closure
test fails on drift, missing files, or manual snapshot edits.
