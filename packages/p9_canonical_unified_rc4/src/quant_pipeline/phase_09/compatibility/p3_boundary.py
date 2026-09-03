from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .errors import ContractMismatchError, PhaseUnavailableError
from .models import CompatibilityReceipt, CompatibilityState
from .runtime import model_data


def _p3_source_root(explicit: str | Path | None = None) -> Path:
    raw = explicit or os.environ.get("P3_COMPAT_SOURCE_ROOT")
    if raw is None:
        raise PhaseUnavailableError(
            "P3 is a legacy regular-package namespace and must be integrated through "
            "an isolated process; configure P3_COMPAT_SOURCE_ROOT"
        )
    root = Path(raw).resolve()
    source = root / "src"
    if not source.is_dir():
        raise PhaseUnavailableError(f"P3 source root is invalid: {root}")
    return root


def _run_p3(script: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    process = subprocess.run(
        [sys.executable, "-I", "-c", script],
        input=json.dumps(payload, ensure_ascii=False, default=str),
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise ContractMismatchError(f"isolated P3 contract validation failed: {detail}")
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ContractMismatchError("isolated P3 bridge returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ContractMismatchError("isolated P3 bridge must return a JSON object")
    return result


_VALIDATE_SCRIPT = r'''
import json, sys
sys.path.insert(0, __import__('os').environ['PYTHONPATH'])
from quant_pipeline.phase_03_agents_rag_memory.s31_models import (
    P9EvaluationEvidenceBundle, P9ContextLearningHandoffManifest,
)
payload=json.load(sys.stdin)
b=P9EvaluationEvidenceBundle.model_validate(payload['bundle'], strict=False)
m=P9ContextLearningHandoffManifest.model_validate(payload['manifest'], strict=False)
if m.bundle_artifact_id != b.artifact_id:
    raise ValueError('manifest does not reference bundle')
if m.run_id != b.run_id or m.cycle_id != b.cycle_id:
    raise ValueError('run/cycle mismatch')
print(json.dumps({'bundle': b.model_dump(mode='json'), 'manifest': m.model_dump(mode='json')}))
'''


_FEEDBACK_SCRIPT = r'''
import json, sys, os
sys.path.insert(0, os.environ['PYTHONPATH'])
from quant_pipeline.phase_03_agents_rag_memory.integration.p9_reference import (
    ReferenceOutcome, build_s3_feedback_handoff,
)
p=json.load(sys.stdin)
outcomes=tuple(ReferenceOutcome.model_validate(x, strict=False) for x in p['outcomes'])
from datetime import datetime
package, handoff=build_s3_feedback_handoff(
    evaluation_bundle=p['bundle'], context_handoff=p['manifest'], outcomes=outcomes,
    evaluated_at=datetime.fromisoformat(p['evaluated_at'].replace('Z','+00:00')),
    source_cycle_id=p['source_cycle_id'],
    experience_available_from_cycle=p['experience_available_from_cycle'],
)
print(json.dumps({'package': package, 'handoff': handoff}))
'''


def validate_p3_evaluation_boundary(
    *,
    evaluation_bundle: Any,
    context_manifest: Any,
    checked_at: datetime,
    p3_source_root: str | Path | None = None,
) -> CompatibilityReceipt:
    root = _p3_source_root(p3_source_root)
    result = _run_p3(
        _VALIDATE_SCRIPT,
        {"bundle": model_data(evaluation_bundle), "manifest": model_data(context_manifest)},
        root,
    )
    bundle = result["bundle"]
    manifest = result["manifest"]
    source_hash = payload_sha256(bundle)
    limitations: list[str] = []
    if manifest["bundle_content_hash"] != source_hash:
        limitations.append(
            "P3 canonicalization differs from P9; the producer hash is retained as external evidence"
        )
    state = CompatibilityState.COMPATIBLE_LIMITED if limitations else CompatibilityState.COMPATIBLE
    return CompatibilityReceipt(
        phase_id="P3",
        package_name="quant-pipeline-p3",
        package_version=str(bundle["pipeline_version"]),
        contract_name="P3_S31_P9_EVALUATION_BOUNDARY_V1",
        contract_version="1.0.0",
        state=state,
        checked_at=checked_at.astimezone(UTC),
        run_id=str(bundle["run_id"]),
        cycle_id=str(bundle["cycle_id"]),
        source_payload_sha256=source_hash,
        limitations=tuple(limitations),
    )


def build_p3_belief_feedback(
    *,
    evaluation_bundle: Any,
    context_manifest: Any,
    outcomes: tuple[Mapping[str, Any], ...],
    evaluated_at: datetime,
    source_cycle_id: int,
    experience_available_from_cycle: int,
    p3_source_root: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _p3_source_root(p3_source_root)
    result = _run_p3(
        _FEEDBACK_SCRIPT,
        {
            "bundle": model_data(evaluation_bundle),
            "manifest": model_data(context_manifest),
            "outcomes": [dict(item) for item in outcomes],
            "evaluated_at": evaluated_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "source_cycle_id": source_cycle_id,
            "experience_available_from_cycle": experience_available_from_cycle,
        },
        root,
    )
    return result["package"], result["handoff"]


def build_p3_retro_context_package(
    *,
    memory_update_id: str,
    retro_package_id: str,
    created_at: datetime,
    valid_from: datetime,
    source_backtest_id: str,
    lineage_id: str,
    memory_items: list[dict[str, Any]],
    hypothesis_items: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    context_tags: list[str],
    pipeline_version: str = "0.1.0rc4.post2",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if valid_from <= created_at:
        raise ContractMismatchError("P3 retro context must become valid after creation")
    package = {
        "memory_update_id": memory_update_id,
        "retro_package_id": retro_package_id,
        "created_at": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "memory_items": memory_items,
        "hypothesis_items": hypothesis_items,
        "evidence_items": evidence_items,
        "agent_instruction_updates": [],
        "context_tags": context_tags,
        "valid_from": valid_from.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "source_backtest_id": source_backtest_id,
        "lineage_id": lineage_id,
        "artifact_id": retro_package_id,
    }
    manifest = {
        "artifact_id": f"p3-retro-manifest-{payload_sha256(package)[:20]}",
        "created_at": package["created_at"],
        "lineage_id": lineage_id,
        "pipeline_version": pipeline_version,
    }
    return package, manifest

_BELIEF_CONSUMER_SCRIPT = r'''
import json, sys, os
sys.path.insert(0, os.environ['PYTHONPATH'])
from quant_pipeline.phase_03_agents_rag_memory.foundation.learning_feedback.belief import ingest_matured_belief_feedback
p=json.load(sys.stdin)
result=ingest_matured_belief_feedback(
    {
        'p9_belief_outcome_feedback_package': p['package'],
        'phase3_learning_feedback_handoff_manifest': p['manifest'],
        'phase3_run_snapshot': p['snapshot'],
    },
    {
        'current_cycle_id': p['current_cycle_id'],
        'processed_at': p['processed_at'],
        'package_root': os.environ['P3_ROOT'],
    },
)
print(json.dumps(result, default=str))
'''

_RETRO_CONSUMER_SCRIPT = r'''
import json, sys, os
sys.path.insert(0, os.environ['PYTHONPATH'])
from quant_pipeline.phase_03_agents_rag_memory.foundation.learning_feedback.retro import ingest_promoted_retro_update
p=json.load(sys.stdin)
result=ingest_promoted_retro_update(
    {
        'retro_memory_update_package': p['package'],
        'phase3_retro_handoff_manifest': p['manifest'],
        'phase3_run_snapshot': p['snapshot'],
        'retro_patch_compatibility_config': p['policy'],
    },
    {
        'current_cycle_id': p['current_cycle_id'],
        'processed_at': p['processed_at'],
        'package_root': os.environ['P3_ROOT'],
    },
)
print(json.dumps(result, default=str))
'''


def _run_p3_root_script(
    script: str,
    payload: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    env = dict(os.environ)
    env['PYTHONPATH'] = str(root / 'src')
    env['P3_ROOT'] = str(root)
    process = subprocess.run(
        [sys.executable, '-I', '-c', script],
        input=json.dumps(payload, ensure_ascii=False, default=str),
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise ContractMismatchError(f'isolated P3 consumer rejected payload: {detail}')
    return json.loads(process.stdout)


def validate_p3_belief_feedback_consumer(
    *,
    package: Mapping[str, Any],
    manifest: Mapping[str, Any],
    phase3_run_snapshot: Mapping[str, Any],
    current_cycle_id: int,
    processed_at: datetime,
    p3_source_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _p3_source_root(p3_source_root)
    return _run_p3_root_script(
        _BELIEF_CONSUMER_SCRIPT,
        {
            'package': dict(package),
            'manifest': dict(manifest),
            'snapshot': dict(phase3_run_snapshot),
            'current_cycle_id': current_cycle_id,
            'processed_at': processed_at.astimezone(UTC).isoformat().replace('+00:00', 'Z'),
        },
        root,
    )


def validate_p3_retro_context_consumer(
    *,
    package: Mapping[str, Any],
    manifest: Mapping[str, Any],
    phase3_run_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    current_cycle_id: int,
    processed_at: datetime,
    p3_source_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _p3_source_root(p3_source_root)
    return _run_p3_root_script(
        _RETRO_CONSUMER_SCRIPT,
        {
            'package': dict(package),
            'manifest': dict(manifest),
            'snapshot': dict(phase3_run_snapshot),
            'policy': dict(policy),
            'current_cycle_id': current_cycle_id,
            'processed_at': processed_at.astimezone(UTC).isoformat().replace('+00:00', 'Z'),
        },
        root,
    )
