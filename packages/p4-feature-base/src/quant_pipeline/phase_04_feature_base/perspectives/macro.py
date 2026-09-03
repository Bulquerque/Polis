from __future__ import annotations
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"macro.growth_state","macro.inflation_state","macro.surprise_state"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        primary=spec.source_feature_ids[0]
        for entity in idx.entities(primary):
            sources=[idx.series(entity,f) for f in spec.source_feature_ids]; dates=sorted(set().union(*(s.index for s in sources)))
            for dt in dates:
                vals=[s.get(dt,float("nan")) for s in sources]
                if spec.observer_id=="macro.surprise_state": value=None if pd.isna(vals[0]) else float(vals[0]); used=1
                elif all(pd.notna(v) for v in vals): value=float(vals[0])+0.5*float(vals[1]); used=2
                else: continue
                req={f:1 for f in spec.source_feature_ids[:used]}; prov=idx.collect(entity_id=entity,decision_time=dt,requirements=req)
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="native_macro_state",sign_convention="STATE_DESCRIPTOR_NOT_RETURN_DIRECTION",provenance=prov,attributes={"contemporaneous_state":True}))
    return out
