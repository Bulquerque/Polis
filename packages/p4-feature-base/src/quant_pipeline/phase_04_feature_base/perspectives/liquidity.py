from __future__ import annotations
import math
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"liquidity.participation","liquidity.price_impact","liquidity.attention_crowding"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        primary=spec.source_feature_ids[0]
        for entity in idx.entities(primary):
            series={f:idx.series(entity,f) for f in spec.source_feature_ids}; dates=sorted(set().union(*(s.index for s in series.values())))
            for dt in dates:
                vals={f:s.get(dt,float("nan")) for f,s in series.items()}; required={}
                if not all(pd.notna(v) for v in vals.values()): continue
                required={f:1 for f in vals}
                if spec.observer_id=="liquidity.participation": value=float(vals[spec.source_feature_ids[0]])*(1+float(vals[spec.source_feature_ids[1]]))
                elif spec.observer_id=="liquidity.price_impact": value=sum(math.log1p(abs(float(v))) for v in vals.values())
                else: value=sum(math.log1p(max(float(v),0)) for v in vals.values())
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements=required)
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="state_score",sign_convention="HIGHER_MEANS_GREATER_PARTICIPATION_IMPACT_OR_CROWDING",provenance=prov,attributes={"proxy":spec.observer_id.endswith("crowding")}))
    return out
