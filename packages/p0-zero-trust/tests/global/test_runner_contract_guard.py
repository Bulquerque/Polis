from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_phase_runners_do_not_contain_notimplementederror():
    runner_files = sorted(ROOT.glob('phase_*/*/src/quant_pipeline/*/runner.py'))
    assert runner_files, 'no phase runners found'

    offending = []
    for path in runner_files:
        if 'NotImplementedError' in path.read_text(encoding='utf-8'):
            offending.append(path)

    assert not offending, offending
