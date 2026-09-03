from __future__ import annotations
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"carry.curve_slope_state","carry.basis_state","carry.option_term_state"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        primary=spec.source_feature_ids[0]
        entities=idx.entities(primary)
        for entity in entities:
            series=[idx.series(entity,f) for f in spec.source_feature_ids]; dates=sorted(set().union(*(s.index for s in series)))
            for dt in dates:
                vals=[s.get(dt,float("nan")) for s in series]
                if not all(pd.notna(v) for v in vals): continue
                value=float(vals[0])-float(vals[1]) if spec.observer_id=="carry.curve_slope_state" else float(vals[0])
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements={f:1 for f in spec.source_feature_ids})
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="carry_state",sign_convention="SIGNED_CARRY_OR_CURVE_STATE_NOT_RETURN_FORECAST",provenance=prov,attributes={"convention_id":spec.parameters.get("convention_id","UNSPECIFIED")}))
    return out
