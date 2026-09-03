# Integration runbook

```bash
python -B tools/generate_contracts.py
python -B tools/generate_wave_0_3_release.py
python -B tools/generate_manifest.py
python -B tools/validate_package.py
```

Run tests in bounded batches on constrained hosts. Do not promote to production.
