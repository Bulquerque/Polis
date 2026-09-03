from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_09.contracts.base import ModuleStatus
from quant_pipeline.phase_09.contracts.integrity import payload_sha256
from quant_pipeline.phase_09.contracts.receipts import (
    ModuleExecutionReceipt,
    SubphaseExecutionReceipt,
    SubphaseExecutionReceiptPayload,
)
from quant_pipeline.phase_09.contracts.s1 import S1ExecutionOutputs
from quant_pipeline.phase_09.subphases.s01_evidence_lineage_replay.clock import ClockPort

from .common import build_integrity, build_module_receipt, source_sha256
from .contracts.base import (
    BudgetState,
    CatalogState,
    ExperimentValidationState,
    RegistryState,
    SearchSpaceState,
    TrialPlanState,
)
from .contracts.budget import BudgetPlanningInput
from .contracts.configuration import ConfigurationBuildInput
from .contracts.experiment import ExperimentValidationInput
from .contracts.parameters import HyperparameterRegistryInput
from .contracts.request import S2RunRequest
from .contracts.search_space import SearchSpaceCompilationInput
from .contracts.trials import (
    FoundationExecutionResult,
    FoundationExperimentBundle,
    FoundationExperimentBundlePayload,
    S2ExecutionOutputs,
    TrialSchedulingInput,
)
from .m01_experiment_validator import ExperimentSpecificationValidator
from .m02_parameter_registry import HyperparameterSchemaRegistry
from .m03_search_space_compiler import ConditionalSearchSpaceCompiler
from .m04_budget_controller import SearchBudgetAndComplexityController
from .m05_configuration_builder import ConfigurationIdentityAndLineageBuilder
from .m06_trial_scheduler import HyperparameterTrialSchedulerAndStateReconciler

EXPECTED_MODULE_IDS = tuple(f"P9.S2.M0{index}" for index in range(1, 7))


class S2Runner:
    """Executes P9.S2 in dependency order and emits the S1-S2 boundary bundle."""

    def __init__(self, *, clock: ClockPort) -> None:
        self._clock = clock
        self._source_root = Path(__file__).resolve().parent

    def run(self, request: S2RunRequest) -> FoundationExecutionResult:
        s1_outputs = request.s1_outputs
        receipts: list[ModuleExecutionReceipt] = []
        limitations: list[str] = []

        if s1_outputs.subphase_receipt.payload.status is not ModuleStatus.SUCCESS:
            receipts.extend(
                self._skipped_receipts(
                    start_index=1,
                    reason_code="P9_S2_S1_NOT_QUALIFIED",
                    limitation="S1 must be SUCCESS before experiment governance",
                )
            )
            outputs = self._outputs(
                receipts=receipts,
                status=ModuleStatus.INVALID,
                reason_codes=("P9_S2_S1_NOT_QUALIFIED",),
                limitations=("S1 did not qualify the evidence foundation",),
            )
            return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=None)
        if s1_outputs.frozen_cohort is None:
            raise ValueError("S1 SUCCESS outputs must contain frozen cohort")

        m01_request = ExperimentValidationInput(
            specification=request.specification,
            frozen_cohort=s1_outputs.frozen_cohort,
            metric_registry=request.metric_registry,
            capability_registry=request.capability_registry,
            promotion_policy=request.promotion_policy,
        )
        m01_start = self._clock.now()
        m01 = ExperimentSpecificationValidator().validate(m01_request)
        m01_status = self._m01_status(m01.report.state)
        m01_output_ids = (
            (f"validated-spec-{m01.validated.specification_sha256}",)
            if m01.validated is not None
            else ()
        )
        receipts.append(
            build_module_receipt(
                module_id="P9.S2.M01",
                status=m01_status,
                started_at=m01_start,
                completed_at=self._clock.now(),
                input_artifact_ids=(s1_outputs.frozen_cohort.cohort_id,),
                output_artifact_ids=m01_output_ids,
                reason_codes=m01.report.reason_codes,
                limitations=m01.report.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m01_experiment_validator.py"
                ),
                policy_sha256=payload_sha256(
                    {
                        "metric_registry": request.metric_registry.registry_sha256,
                        "capability_registry": request.capability_registry.registry_sha256,
                        "promotion_policy": request.promotion_policy,
                    }
                ),
            )
        )
        limitations.extend(m01.report.limitations)
        if m01.validated is None:
            receipts.extend(
                self._skipped_receipts(
                    start_index=2,
                    reason_code="P9_S2_SPEC_NOT_VALIDATED",
                    limitation="experiment specification gate blocked downstream modules",
                )
            )
            outputs = self._outputs(
                receipts=receipts,
                status=m01_status,
                reason_codes=m01.report.reason_codes,
                limitations=tuple(limitations),
            )
            return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=None)

        m02_request = HyperparameterRegistryInput(
            validated_specification=m01.validated,
            phase_contracts=request.phase_parameter_contracts,
            deprecations=request.deprecation_registry,
        )
        m02_start = self._clock.now()
        m02 = HyperparameterSchemaRegistry().build(m02_request)
        m02_status = self._m02_status(m02.compatibility_report.state)
        m02_output_ids = (
            (m02.snapshot.snapshot_id,) if m02.snapshot is not None else ()
        )
        receipts.append(
            build_module_receipt(
                module_id="P9.S2.M02",
                status=m02_status,
                started_at=m02_start,
                completed_at=self._clock.now(),
                input_artifact_ids=m01_output_ids,
                output_artifact_ids=m02_output_ids,
                reason_codes=m02.compatibility_report.reason_codes,
                limitations=m02.compatibility_report.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m02_parameter_registry.py"
                ),
                policy_sha256=payload_sha256(
                    {
                        "phase_contracts": request.phase_parameter_contracts,
                        "deprecations": request.deprecation_registry,
                    }
                ),
            )
        )
        limitations.extend(m02.compatibility_report.limitations)
        if m02.snapshot is None:
            receipts.extend(
                self._skipped_receipts(
                    start_index=3,
                    reason_code="P9_S2_PARAMETER_REGISTRY_BLOCKED",
                    limitation="parameter registry blocked search-space compilation",
                )
            )
            outputs = self._outputs(
                receipts=receipts,
                status=m02_status,
                validated=m01.validated,
                reason_codes=m02.compatibility_report.reason_codes,
                limitations=tuple(limitations),
            )
            return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=None)

        m03_request = SearchSpaceCompilationInput(
            validated_specification=m01.validated,
            parameter_snapshot=m02.snapshot,
            declaration=request.search_space_declaration,
        )
        m03_start = self._clock.now()
        m03 = ConditionalSearchSpaceCompiler().compile(m03_request)
        compiled = m03.compiled_space
        if compiled is None:
            raise RuntimeError("search-space compiler returned no result")
        m03_status = self._m03_status(compiled.state)
        receipts.append(
            build_module_receipt(
                module_id="P9.S2.M03",
                status=m03_status,
                started_at=m03_start,
                completed_at=self._clock.now(),
                input_artifact_ids=m02_output_ids,
                output_artifact_ids=(compiled.space_id,),
                reason_codes=compiled.reason_codes,
                limitations=compiled.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m03_search_space_compiler.py"
                ),
                policy_sha256=payload_sha256(request.search_space_declaration),
            )
        )
        limitations.extend(compiled.limitations)
        if m03_status in {ModuleStatus.INVALID, ModuleStatus.UNAVAILABLE}:
            receipts.extend(
                self._skipped_receipts(
                    start_index=4,
                    reason_code="P9_S2_SEARCH_SPACE_BLOCKED",
                    limitation="compiled search space is not executable",
                )
            )
            outputs = self._outputs(
                receipts=receipts,
                status=m03_status,
                validated=m01.validated,
                parameter_snapshot=m02.snapshot,
                compiled_search_space=compiled,
                reason_codes=compiled.reason_codes,
                limitations=tuple(limitations),
            )
            return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=None)

        m04_request = BudgetPlanningInput(
            validated_specification=m01.validated,
            compiled_search_space=compiled,
            resource_capacity=request.resource_capacity,
            budget_policy=request.budget_policy,
            fidelity_levels=request.fidelity_levels,
            early_stopping=request.early_stopping_policy,
        )
        m04_start = self._clock.now()
        m04 = SearchBudgetAndComplexityController().plan(m04_request)
        m04_status = self._m04_status(m04.report.state)
        m04_output_ids = (
            (m04.budget_plan.plan_id,) if m04.budget_plan is not None else ()
        )
        receipts.append(
            build_module_receipt(
                module_id="P9.S2.M04",
                status=m04_status,
                started_at=m04_start,
                completed_at=self._clock.now(),
                input_artifact_ids=(compiled.space_id,),
                output_artifact_ids=m04_output_ids,
                reason_codes=m04.report.reason_codes,
                limitations=m04.report.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m04_budget_controller.py"
                ),
                policy_sha256=request.budget_policy.policy_sha256,
            )
        )
        limitations.extend(m04.report.limitations)
        if m04.budget_plan is None:
            receipts.extend(
                self._skipped_receipts(
                    start_index=5,
                    reason_code="P9_S2_BUDGET_BLOCKED",
                    limitation="search budget is not executable",
                )
            )
            outputs = self._outputs(
                receipts=receipts,
                status=m04_status,
                validated=m01.validated,
                parameter_snapshot=m02.snapshot,
                compiled_search_space=compiled,
                reason_codes=m04.report.reason_codes,
                limitations=tuple(limitations),
            )
            return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=None)

        m05_request = ConfigurationBuildInput(
            compiled_search_space=compiled,
            parameter_snapshot=m02.snapshot,
            budget_plan=m04.budget_plan,
            identity_context=request.identity_context,
        )
        m05_start = self._clock.now()
        m05 = ConfigurationIdentityAndLineageBuilder().build(m05_request)
        catalog = m05.catalog
        if catalog is None:
            raise RuntimeError("configuration builder returned no catalog")
        m05_status = self._m05_status(catalog.state)
        receipts.append(
            build_module_receipt(
                module_id="P9.S2.M05",
                status=m05_status,
                started_at=m05_start,
                completed_at=self._clock.now(),
                input_artifact_ids=(compiled.space_id, m04.budget_plan.plan_id),
                output_artifact_ids=(catalog.catalog_id,),
                reason_codes=catalog.reason_codes,
                limitations=catalog.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m05_configuration_builder.py"
                ),
                policy_sha256=payload_sha256(request.identity_context),
            )
        )
        limitations.extend(catalog.limitations)
        if m05_status is ModuleStatus.INVALID:
            receipts.extend(
                self._skipped_receipts(
                    start_index=6,
                    reason_code="P9_S2_CONFIGURATION_CATALOG_BLOCKED",
                    limitation="configuration identity gate blocked scheduling",
                )
            )
            outputs = self._outputs(
                receipts=receipts,
                status=m05_status,
                validated=m01.validated,
                parameter_snapshot=m02.snapshot,
                compiled_search_space=compiled,
                budget_plan=m04.budget_plan,
                configuration_catalog=catalog,
                reason_codes=catalog.reason_codes,
                limitations=tuple(limitations),
            )
            return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=None)

        m06_request = TrialSchedulingInput(
            validated_specification=m01.validated,
            configuration_catalog=catalog,
            budget_plan=m04.budget_plan,
            compiled_search_space=compiled,
            scheduler_policy=request.scheduler_policy,
            worker_capabilities=request.worker_capabilities,
            seed_policy=request.seed_policy,
        )
        m06_start = self._clock.now()
        m06 = HyperparameterTrialSchedulerAndStateReconciler().schedule(m06_request)
        m06_status = self._m06_status(m06.report.state)
        output_ids = ()
        if m06.trial_plan is not None and m06.trial_state_ledger is not None:
            output_ids = (m06.trial_plan.plan_id, m06.trial_state_ledger.ledger_id)
        receipts.append(
            build_module_receipt(
                module_id="P9.S2.M06",
                status=m06_status,
                started_at=m06_start,
                completed_at=self._clock.now(),
                input_artifact_ids=(catalog.catalog_id, m04.budget_plan.plan_id),
                output_artifact_ids=output_ids,
                reason_codes=m06.report.reason_codes,
                limitations=m06.report.limitations,
                implementation_sha256=self._implementation_sha256(
                    "m06_trial_scheduler.py"
                ),
                policy_sha256=payload_sha256(
                    {
                        "scheduler_policy": request.scheduler_policy,
                        "worker_capabilities": request.worker_capabilities,
                        "seed_policy": request.seed_policy,
                    }
                ),
            )
        )
        limitations.extend(m06.report.limitations)
        status = self._aggregate_status(receipts)
        outputs = self._outputs(
            receipts=receipts,
            status=status,
            validated=m01.validated,
            parameter_snapshot=m02.snapshot,
            compiled_search_space=compiled,
            budget_plan=m04.budget_plan,
            configuration_catalog=catalog,
            trial_plan=m06.trial_plan,
            trial_state_ledger=m06.trial_state_ledger,
            reason_codes=m06.report.reason_codes,
            limitations=tuple(limitations),
        )
        bundle = self._bundle(s1_outputs, outputs) if m06.trial_plan is not None else None
        return FoundationExecutionResult(s2_outputs=outputs, foundation_bundle=bundle)

    def _outputs(
        self,
        *,
        receipts: list[ModuleExecutionReceipt],
        status: ModuleStatus,
        validated=None,
        parameter_snapshot=None,
        compiled_search_space=None,
        budget_plan=None,
        configuration_catalog=None,
        trial_plan=None,
        trial_state_ledger=None,
        reason_codes: tuple[str, ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> S2ExecutionOutputs:
        subphase_payload = SubphaseExecutionReceiptPayload(
            subphase_id="P9.S2",
            expected_module_ids=EXPECTED_MODULE_IDS,
            module_receipts=tuple(receipts),
            status=status,
            output_artifact_ids=tuple(
                artifact_id
                for receipt in receipts
                for artifact_id in receipt.payload.output_artifact_ids
            ),
            reason_codes=reason_codes if status is not ModuleStatus.SUCCESS else (),
            limitations=tuple(dict.fromkeys(limitations)),
        )
        subphase = SubphaseExecutionReceipt(
            payload=subphase_payload,
            integrity=build_integrity(subphase_payload),
        )
        return S2ExecutionOutputs(
            validated_specification=validated,
            parameter_snapshot=parameter_snapshot,
            compiled_search_space=compiled_search_space,
            budget_plan=budget_plan,
            configuration_catalog=configuration_catalog,
            trial_plan=trial_plan,
            trial_state_ledger=trial_state_ledger,
            module_receipts=tuple(receipts),
            subphase_receipt=subphase,
            limitations=tuple(dict.fromkeys(limitations)),
        )

    @staticmethod
    def _bundle(
        s1_outputs: S1ExecutionOutputs,
        s2_outputs: S2ExecutionOutputs,
    ) -> FoundationExperimentBundle:
        validated_handoff = s1_outputs.validated_handoff
        if validated_handoff is None:
            raise ValueError("S1 outputs do not contain validated handoff")
        s1_hash = payload_sha256(s1_outputs)
        s2_hash = payload_sha256(s2_outputs)
        payload = FoundationExperimentBundlePayload(
            run_id=validated_handoff.handoff.run_id,
            cycle_id=validated_handoff.handoff.cycle_id,
            s1_outputs_sha256=s1_hash,
            s2_outputs_sha256=s2_hash,
            s1_outputs=s1_outputs,
            s2_outputs=s2_outputs,
            input_bundle_sha256=s1_hash,
            limitations=tuple(
                dict.fromkeys(s1_outputs.limitations + s2_outputs.limitations)
            ),
        )
        return FoundationExperimentBundle(
            payload=payload,
            integrity=build_integrity(payload),
        )

    def _skipped_receipts(
        self,
        *,
        start_index: int,
        reason_code: str,
        limitation: str,
    ) -> list[ModuleExecutionReceipt]:
        return [
            build_module_receipt(
                module_id=f"P9.S2.M0{index}",
                status=ModuleStatus.SKIPPED_UPSTREAM_BLOCKED,
                started_at=self._clock.now(),
                completed_at=self._clock.now(),
                reason_codes=(reason_code,),
                limitations=(limitation,),
                implementation_sha256=self._implementation_sha256(
                    {
                        1: "m01_experiment_validator.py",
                        2: "m02_parameter_registry.py",
                        3: "m03_search_space_compiler.py",
                        4: "m04_budget_controller.py",
                        5: "m05_configuration_builder.py",
                        6: "m06_trial_scheduler.py",
                    }[index]
                ),
                policy_sha256="0" * 64,
            )
            for index in range(start_index, 7)
        ]

    def _implementation_sha256(self, filename: str) -> str:
        return source_sha256(self._source_root / filename)

    @staticmethod
    def _aggregate_status(receipts: list[ModuleExecutionReceipt]) -> ModuleStatus:
        statuses = {receipt.payload.status for receipt in receipts}
        for status in (
            ModuleStatus.FAILED,
            ModuleStatus.INVALID,
            ModuleStatus.UNAVAILABLE,
            ModuleStatus.INSUFFICIENT_EVIDENCE,
            ModuleStatus.LIMITED,
        ):
            if status in statuses:
                return status
        return ModuleStatus.SUCCESS

    @staticmethod
    def _m01_status(state: ExperimentValidationState) -> ModuleStatus:
        return {
            ExperimentValidationState.SPEC_VALID: ModuleStatus.SUCCESS,
            ExperimentValidationState.SPEC_VALID_WITH_LIMITATIONS: ModuleStatus.LIMITED,
            ExperimentValidationState.CAPABILITY_UNAVAILABLE: ModuleStatus.UNAVAILABLE,
            ExperimentValidationState.HOLDOUT_POLICY_INVALID: ModuleStatus.INVALID,
            ExperimentValidationState.SPEC_INVALID: ModuleStatus.INVALID,
        }[state]

    @staticmethod
    def _m02_status(state: RegistryState) -> ModuleStatus:
        return {
            RegistryState.REGISTRY_SNAPSHOT_READY: ModuleStatus.SUCCESS,
            RegistryState.REGISTRY_LIMITED: ModuleStatus.LIMITED,
            RegistryState.PARAMETER_SCHEMA_INCOMPATIBLE: ModuleStatus.INVALID,
            RegistryState.PARAMETER_DEPRECATED_BLOCKING: ModuleStatus.INVALID,
        }[state]

    @staticmethod
    def _m03_status(state: SearchSpaceState) -> ModuleStatus:
        return {
            SearchSpaceState.SPACE_COMPILED: ModuleStatus.SUCCESS,
            SearchSpaceState.SPACE_COMPILED_WITH_WARNINGS: ModuleStatus.LIMITED,
            SearchSpaceState.SPACE_EMPTY: ModuleStatus.INVALID,
            SearchSpaceState.SPACE_EXPLOSIVE: ModuleStatus.INVALID,
            SearchSpaceState.SPACE_INVALID: ModuleStatus.INVALID,
        }[state]

    @staticmethod
    def _m04_status(state: BudgetState) -> ModuleStatus:
        return {
            BudgetState.BUDGET_RESERVED: ModuleStatus.SUCCESS,
            BudgetState.BUDGET_LIMITED: ModuleStatus.LIMITED,
            BudgetState.BUDGET_INFEASIBLE: ModuleStatus.INVALID,
            BudgetState.RESOURCE_CAPABILITY_UNAVAILABLE: ModuleStatus.UNAVAILABLE,
        }[state]

    @staticmethod
    def _m05_status(state: CatalogState) -> ModuleStatus:
        return {
            CatalogState.CATALOG_READY: ModuleStatus.SUCCESS,
            CatalogState.CATALOG_WITH_EQUIVALENCES: ModuleStatus.LIMITED,
            CatalogState.IDENTITY_COLLISION: ModuleStatus.INVALID,
            CatalogState.LINEAGE_INVALID: ModuleStatus.INVALID,
        }[state]

    @staticmethod
    def _m06_status(state: TrialPlanState) -> ModuleStatus:
        return {
            TrialPlanState.PLAN_READY: ModuleStatus.SUCCESS,
            TrialPlanState.PLAN_READY_LIMITED: ModuleStatus.LIMITED,
            TrialPlanState.NO_TRIALS_VALID: ModuleStatus.INVALID,
            TrialPlanState.SCHEDULER_INFEASIBLE: ModuleStatus.INVALID,
            TrialPlanState.BUNDLE_INVALID: ModuleStatus.INVALID,
        }[state]
