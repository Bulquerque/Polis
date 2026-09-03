from __future__ import annotations

from typing import Any
import pandas as pd

from .perspective_protocol import perspective_lineage_hash
from .atomic_inputs import PerspectiveProvenance
from .economic_models import MissingnessState, QualityState
from .perspective_models import PerspectiveFeatureRecord, PerspectiveSpec


def one_perspective(*,decision_time,entity_id:str,spec:PerspectiveSpec,value:float|None,unit:str,sign_convention:str,provenance:PerspectiveProvenance,attributes:dict[str,Any]|None=None) -> PerspectiveFeatureRecord:
    observed=value is not None and not pd.isna(value)
    return PerspectiveFeatureRecord(
        decision_time=decision_time,entity_id=entity_id,feature_id=spec.feature_id,hypothesis_id=spec.hypothesis_id,
        phenomenon_id=spec.phenomenon_id,perspective_id=spec.perspective_id,observer_id=spec.observer_id,
        parameterization_id=spec.parameterization_id,horizon_group=spec.horizon_group,
        value=float(value) if observed else None,unit=unit,sign_convention=sign_convention,available_at=provenance.available_at,
        source_modalities=provenance.modalities,source_feature_ids=provenance.feature_ids,
        quality_state=provenance.quality_state if observed else QualityState.DEGRADED,
        missingness_state=MissingnessState.OBSERVED if observed else MissingnessState.STRUCTURALLY_MISSING,
        record_lineage_id=perspective_lineage_hash(provenance.lineage_ids),attributes=attributes or {},
    )
