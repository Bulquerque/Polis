from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .contracts.base import CatalogState, SearchStrategy
from .contracts.configuration import (
    ConfigurationBuildInput,
    ConfigurationBuildOutcome,
    ConfigurationCatalog,
    ConfigurationIdentityReceipt,
    ConfigurationLineageGraph,
    ConfigurationRecord,
    EconomicEquivalenceGroups,
    ParameterAssignment,
)
from .contracts.parameters import ParameterScalar
from .sampling import (
    boundary_parameter_ids,
    iter_grid_assignments,
    take_unique_random_assignments,
)

HashFunction = Callable[[object], str]


class ConfigurationIdentityAndLineageBuilder:
    """Builds content-addressed configurations from active parameters only."""

    def __init__(self, hash_function: HashFunction = payload_sha256) -> None:
        self._hash_function = hash_function

    def build(self, request: ConfigurationBuildInput) -> ConfigurationBuildOutcome:
        strategy = request.budget_plan.search_strategy
        limit = request.budget_plan.configuration_limit
        if limit < 1:
            return self._empty_outcome(request, "P9_S2_CONFIG_NO_BUDGET")

        if strategy is SearchStrategy.GRID:
            proposals = tuple(
                assignment
                for index, assignment in enumerate(
                    iter_grid_assignments(request.compiled_search_space)
                )
                if index < limit
            )
        elif strategy in {
            SearchStrategy.RANDOM,
            SearchStrategy.SUCCESSIVE_HALVING,
            SearchStrategy.HYPERBAND,
        }:
            seed = self._derived_seed(request)
            proposals = take_unique_random_assignments(
                request.compiled_search_space,
                count=limit,
                seed=seed,
            )
        else:
            return self._empty_outcome(request, "P9_S2_CONFIG_STRATEGY_UNAVAILABLE")

        if not proposals:
            return self._empty_outcome(request, "P9_S2_CONFIG_NO_VALID_PROPOSALS")

        configurations: list[ConfigurationRecord] = []
        preimages_by_id: dict[str, str] = {}
        duplicate_proposals = limit - len(proposals) if len(proposals) < limit else 0
        collision = False
        for source_index, assignment in enumerate(proposals):
            record = self._record(request, assignment, source_index)
            existing_preimage = preimages_by_id.get(record.configuration_id)
            if existing_preimage is not None:
                if existing_preimage != record.identity_preimage_sha256:
                    collision = True
                    break
                duplicate_proposals += 1
                continue
            preimages_by_id[record.configuration_id] = record.identity_preimage_sha256
            configurations.append(record)

        if collision:
            catalog = self._catalog(
                request,
                (),
                CatalogState.IDENTITY_COLLISION,
                ("P9_S2_CONFIG_ID_COLLISION",),
            )
            return ConfigurationBuildOutcome(
                catalog=catalog,
                lineage_graph=None,
                equivalence_groups=None,
                identity_receipt=None,
            )

        boundary_count = sum(bool(record.boundary_parameter_ids) for record in configurations)
        limitations: tuple[str, ...] = ()
        state = CatalogState.CATALOG_READY
        if duplicate_proposals:
            state = CatalogState.CATALOG_WITH_EQUIVALENCES
            limitations = (
                "duplicate random proposals were discarded after canonicalization",
            )
        catalog = self._catalog(
            request,
            tuple(configurations),
            state,
            (),
            limitations=limitations,
        )
        graph = ConfigurationLineageGraph(
            configuration_ids=tuple(record.configuration_id for record in configurations),
            edges=(),
        )
        groups = EconomicEquivalenceGroups(groups=())
        receipt_preimage = {
            "catalog_id": catalog.catalog_id,
            "generated_count": len(configurations),
            "duplicate_proposals_discarded": duplicate_proposals,
            "boundary_configuration_count": boundary_count,
        }
        receipt_hash = payload_sha256(receipt_preimage)
        receipt = ConfigurationIdentityReceipt(
            catalog_id=catalog.catalog_id,
            generated_count=len(configurations),
            duplicate_proposals_discarded=duplicate_proposals,
            boundary_configuration_count=boundary_count,
            receipt_sha256=receipt_hash,
        )
        return ConfigurationBuildOutcome(
            catalog=catalog,
            lineage_graph=graph,
            equivalence_groups=groups,
            identity_receipt=receipt,
        )

    def _record(
        self,
        request: ConfigurationBuildInput,
        assignment: Mapping[str, ParameterScalar],
        source_index: int,
    ) -> ConfigurationRecord:
        ordered_assignments = tuple(
            ParameterAssignment(parameter_id=parameter_id, value=value)
            for parameter_id, value in sorted(assignment.items())
        )
        preimage = {
            "experiment_id": request.compiled_search_space.experiment_id,
            "assignments": ordered_assignments,
            "parameter_snapshot_sha256": request.parameter_snapshot.snapshot_sha256,
            "search_space_sha256": request.compiled_search_space.space_sha256,
            "budget_plan_sha256": request.budget_plan.plan_sha256,
            "code_artifact_sha256": request.identity_context.code_artifact.content_sha256,
            "data_artifact_sha256": request.identity_context.data_snapshot.content_sha256,
            "fold_plan_sha256": request.identity_context.fold_plan.request_sha256,
            "seed_policy_sha256": request.identity_context.seed_policy.policy_sha256,
            "policy_bundle_sha256": request.identity_context.policy_bundle_sha256,
        }
        identity_preimage_sha256 = payload_sha256(preimage)
        configuration_hash = self._hash_function(preimage)
        return ConfigurationRecord(
            configuration_id=f"cfg-{configuration_hash}",
            experiment_id=request.compiled_search_space.experiment_id,
            assignments=ordered_assignments,
            active_parameter_ids=tuple(
                assignment.parameter_id for assignment in ordered_assignments
            ),
            source=request.budget_plan.search_strategy.value,
            source_index=source_index,
            boundary_parameter_ids=boundary_parameter_ids(
                assignment,
                request.compiled_search_space.parameters,
            ),
            identity_preimage_sha256=identity_preimage_sha256,
        )

    @staticmethod
    def _derived_seed(request: ConfigurationBuildInput) -> int:
        seed_material = (
            f"{request.identity_context.seed_policy.base_seed}:"
            f"{request.compiled_search_space.experiment_id}:"
            f"{request.compiled_search_space.space_sha256}"
        ).encode("utf-8")
        return int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")

    @staticmethod
    def _catalog(
        request: ConfigurationBuildInput,
        configurations: tuple[ConfigurationRecord, ...],
        state: CatalogState,
        reasons: tuple[str, ...],
        *,
        limitations: tuple[str, ...] = (),
    ) -> ConfigurationCatalog:
        catalog_preimage = {
            "experiment_id": request.compiled_search_space.experiment_id,
            "state": state,
            "configurations": configurations,
            "reason_codes": reasons,
            "limitations": limitations,
        }
        catalog_hash = payload_sha256(catalog_preimage)
        return ConfigurationCatalog(
            catalog_id=f"configuration-catalog-{catalog_hash}",
            experiment_id=request.compiled_search_space.experiment_id,
            state=state,
            configurations=configurations,
            catalog_sha256=catalog_hash,
            reason_codes=reasons,
            limitations=limitations,
        )

    def _empty_outcome(
        self,
        request: ConfigurationBuildInput,
        reason: str,
    ) -> ConfigurationBuildOutcome:
        catalog = self._catalog(
            request,
            (),
            CatalogState.LINEAGE_INVALID,
            (reason,),
        )
        return ConfigurationBuildOutcome(
            catalog=catalog,
            lineage_graph=None,
            equivalence_groups=None,
            identity_receipt=None,
        )
