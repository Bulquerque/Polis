from __future__ import annotations

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .contracts.base import CapabilityState, RegistryState
from .contracts.parameters import (
    HyperparameterRegistryInput,
    HyperparameterRegistryOutcome,
    HyperparameterSchemaSnapshot,
    ParameterAuthorityBinding,
    ParameterAuthorityMap,
    ParameterCompatibilityIssue,
    ParameterCompatibilityReport,
)


class HyperparameterSchemaRegistry:
    """Freezes public P5-P8 parameter contracts without redefining their semantics."""

    def build(self, request: HyperparameterRegistryInput) -> HyperparameterRegistryOutcome:
        target_phases = {
            module_id.split(".", 1)[0]
            for module_id in request.validated_specification.specification.target_module_ids
        }
        definitions = []
        issues: list[ParameterCompatibilityIssue] = []
        capability_by_parameter: dict[str, CapabilityState] = {}

        snapshots_by_phase = {
            snapshot.phase_id: snapshot
            for snapshot in request.phase_contracts.snapshots
        }
        for phase in sorted(target_phases):
            snapshot = snapshots_by_phase.get(phase)
            if snapshot is None:
                issues.append(
                    ParameterCompatibilityIssue(
                        parameter_id=f"{phase}.missing.contract",
                        reason_code="P9_S2_PARAMETER_CONTRACT_MISSING",
                        description=f"public parameter contract for {phase} is missing",
                        blocking=True,
                    )
                )
                continue
            for definition in snapshot.parameters:
                definitions.append(definition)
                capability_by_parameter[definition.parameter_id] = snapshot.capability_state

        canonical_ids = [definition.parameter_id for definition in definitions]
        if len(canonical_ids) != len(set(canonical_ids)):
            duplicates = sorted(
                parameter_id
                for parameter_id in set(canonical_ids)
                if canonical_ids.count(parameter_id) > 1
            )
            for parameter_id in duplicates:
                issues.append(
                    ParameterCompatibilityIssue(
                        parameter_id=parameter_id,
                        reason_code="P9_S2_PARAMETER_DUPLICATE",
                        description="parameter appears in more than one public contract",
                        blocking=True,
                    )
                )

        aliases: dict[str, str] = {}
        for definition in definitions:
            for alias in definition.aliases:
                if alias in aliases and aliases[alias] != definition.parameter_id:
                    issues.append(
                        ParameterCompatibilityIssue(
                            parameter_id=alias,
                            reason_code="P9_S2_PARAMETER_ALIAS_AMBIGUOUS",
                            description="alias resolves to more than one canonical parameter",
                            blocking=True,
                        )
                    )
                aliases[alias] = definition.parameter_id

        deprecations = {
            entry.deprecated_parameter_id: entry
            for entry in request.deprecations.entries
        }
        canonical_set = set(canonical_ids)
        for definition in definitions:
            registry_entry = deprecations.get(definition.parameter_id)
            if definition.deprecated:
                if registry_entry is None:
                    issues.append(
                        ParameterCompatibilityIssue(
                            parameter_id=definition.parameter_id,
                            reason_code="P9_S2_PARAMETER_DEPRECATION_UNREGISTERED",
                            description="deprecated parameter is absent from deprecation registry",
                            blocking=True,
                        )
                    )
                elif registry_entry.replacement_parameter_id not in canonical_set:
                    issues.append(
                        ParameterCompatibilityIssue(
                            parameter_id=definition.parameter_id,
                            reason_code="P9_S2_PARAMETER_REPLACEMENT_MISSING",
                            description="deprecated parameter replacement is not in snapshot",
                            blocking=True,
                        )
                    )
            if definition.capability_id is not None:
                state = capability_by_parameter[definition.parameter_id]
                if state in {CapabilityState.UNAVAILABLE, CapabilityState.RESERVED}:
                    issues.append(
                        ParameterCompatibilityIssue(
                            parameter_id=definition.parameter_id,
                            reason_code="P9_S2_PARAMETER_CAPABILITY_UNAVAILABLE",
                            description="parameter belongs to unavailable/reserved capability",
                            blocking=False,
                        )
                    )

        blocking_issues = [issue for issue in issues if issue.blocking]
        deprecated_blocking = any(
            issue.reason_code.startswith("P9_S2_PARAMETER_DEPRECATION")
            or issue.reason_code == "P9_S2_PARAMETER_REPLACEMENT_MISSING"
            for issue in blocking_issues
        )
        if deprecated_blocking:
            state = RegistryState.PARAMETER_DEPRECATED_BLOCKING
        elif blocking_issues:
            state = RegistryState.PARAMETER_SCHEMA_INCOMPATIBLE
        elif issues:
            state = RegistryState.REGISTRY_LIMITED
        else:
            state = RegistryState.REGISTRY_SNAPSHOT_READY

        report = ParameterCompatibilityReport(
            state=state,
            issues=tuple(issues),
            reason_codes=tuple(sorted({issue.reason_code for issue in blocking_issues})),
            limitations=tuple(issue.description for issue in issues if not issue.blocking),
        )
        if blocking_issues:
            return HyperparameterRegistryOutcome(
                snapshot=None,
                compatibility_report=report,
                authority_map=None,
            )

        ordered_definitions = tuple(sorted(definitions, key=lambda item: item.parameter_id))
        snapshot_preimage = {
            "experiment_id": request.validated_specification.specification.experiment_id,
            "specification_sha256": request.validated_specification.specification_sha256,
            "definitions": ordered_definitions,
            "phase_contract_hashes": tuple(
                sorted(
                    (snapshot.phase_id, snapshot.contract_sha256)
                    for snapshot in request.phase_contracts.snapshots
                    if snapshot.phase_id in target_phases
                )
            ),
            "deprecation_registry_sha256": request.deprecations.registry_sha256,
        }
        snapshot_sha = payload_sha256(snapshot_preimage)
        snapshot = HyperparameterSchemaSnapshot(
            snapshot_id=f"parameter-snapshot-{snapshot_sha}",
            experiment_id=request.validated_specification.specification.experiment_id,
            snapshot_sha256=snapshot_sha,
            definitions=ordered_definitions,
        )
        authority = ParameterAuthorityMap(
            bindings=tuple(
                ParameterAuthorityBinding(
                    parameter_id=definition.parameter_id,
                    owner_module_id=definition.owner_module_id,
                    capability_id=definition.capability_id,
                    capability_state=capability_by_parameter[definition.parameter_id],
                )
                for definition in ordered_definitions
            )
        )
        return HyperparameterRegistryOutcome(
            snapshot=snapshot,
            compatibility_report=report,
            authority_map=authority,
        )
