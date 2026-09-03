from __future__ import annotations
import math
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"narrative.information_state","narrative.disagreement_state","narrative.shift_state"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        primary=spec.source_feature_ids[0]
        for entity in idx.entities(primary):
            series=[idx.series(entity,f) for f in spec.source_feature_ids]; dates=sorted(set().union(*(s.index for s in series)))
            for dt in dates:
                vals=[s.get(dt,float("nan")) for s in series]
                if not all(pd.notna(v) for v in vals): continue
                value=float(vals[0]) if len(vals)==1 else float(vals[0])*math.log1p(max(float(vals[1]),0))
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements={f:1 for f in spec.source_feature_ids})
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="narrative_state",sign_convention="STATE_DESCRIPTOR_PRESERVES_SIGN",provenance=prov,attributes={"no_future_outcome_calibration":True}))
    return out
