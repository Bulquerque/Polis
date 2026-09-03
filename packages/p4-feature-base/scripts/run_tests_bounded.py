#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class TestLayer:
    name: str
    path: str
    timeout_seconds: int


LAYERS = (
    TestLayer("integrated_pipeline", "tests/test_integrated_pipeline.py", 90),
    TestLayer("v14_9_corrections", "tests/test_v149_corrections.py", 60),
    TestLayer("release_structure", "tests/test_release_structure.py", 60),
)


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    pythonpath = [str(ROOT / "src"), str(ROOT / "tests")]
    if inherited_pythonpath:
        pythonpath.append(inherited_pythonpath)
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(pythonpath),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _terminate_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def _run_layer(layer: TestLayer, env: dict[str, str]) -> int:
    command = [
        sys.executable,
        "-u",
        "-m",
        "pytest",
        "-p",
        "force_exit_plugin",
        "-q",
        layer.path,
        "--durations=20",
        "-p",
        "no:cacheprovider",
    ]
    print(f"TEST LAYER: {layer.name}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=layer.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        if partial:
            print(partial, end="" if partial.endswith("\n") else "\n", flush=True)
        _terminate_group(process)
        print(
            f"TEST LAYER TIMEOUT: {layer.name} after {layer.timeout_seconds}s",
            file=sys.stderr,
            flush=True,
        )
        return 124
    if output:
        print(output, end="" if output.endswith("\n") else "\n", flush=True)
    return int(process.returncode or 0)


def _selected_layers(names: list[str] | None) -> tuple[TestLayer, ...]:
    if not names:
        return LAYERS
    by_name = {layer.name: layer for layer in LAYERS}
    return tuple(by_name[name] for name in names)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated bounded P4 test layers.")
    parser.add_argument(
        "--layer",
        action="append",
        choices=[layer.name for layer in LAYERS],
        help="Run only the named layer; repeat the option to select multiple layers.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    env = _environment()
    for layer in _selected_layers(args.layer):
        return_code = _run_layer(layer, env)
        if return_code != 0:
            return return_code
    print("BOUNDED TEST SUITE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
