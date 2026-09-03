from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_full_runner_is_reproducible_in_clean_subprocess(tmp_path) -> None:
    project = Path(__file__).parents[3]
    script = tmp_path / "probe.py"
    script.write_text(
        """
import json
from tests.s01.conftest import build_full_fixture
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.runner import S1Runner
f=build_full_fixture()
r=S1Runner(artifact_store=f.store, compatibility=f.compatibility, module_registry=f.module_registry, schema_registry=f.schema_registry, clock=f.clock)
o=r.run(handoff=f.handoff, lineage_policy=f.lineage_policy, replay_policy=f.replay_policy, maturity_policies=f.maturity_policies, commitments=f.commitments, cohort_policies=f.cohort_policies, holdout_access=f.holdout_access, evaluation_as_of=f.evaluation_as_of)
print(json.dumps({"status": o.subphase_receipt.payload.status.value, "cohort": o.frozen_cohort.cohort_sha256, "replay": o.replay_hashes.reconstructed_state_sha256}, sort_keys=True))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(project / "src"), str(project)))
    first = subprocess.check_output([sys.executable, str(script)], env=env, text=True)
    second = subprocess.check_output([sys.executable, str(script)], env=env, text=True)
    assert json.loads(first) == json.loads(second)
    assert json.loads(first)["status"] == "SUCCESS"
