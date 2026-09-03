from __future__ import annotations
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"fundamental.value_state","fundamental.profitability_state","fundamental.investment_state","fundamental.accrual_quality_state"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        primary=spec.source_feature_ids[0]
        for entity in idx.entities(primary):
            series=[idx.series(entity,f) for f in spec.source_feature_ids]; dates=sorted(set().union(*(s.index for s in series)))
            for dt in dates:
                vals=[s.get(dt,float("nan")) for s in series]
                if not all(pd.notna(v) for v in vals): continue
                if spec.observer_id in {"fundamental.value_state","fundamental.profitability_state"}: value=sum(map(float,vals))/len(vals)
                elif spec.observer_id=="fundamental.investment_state": value=-float(vals[0])
                else: value=-abs(float(vals[0]))
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements={f:1 for f in spec.source_feature_ids})
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="fundamental_state",sign_convention="HIGHER_MEANS_STRONGER_VALUE_QUALITY_OR_CONSERVATIVE_INVESTMENT",provenance=prov,attributes={"point_in_time_fundamentals":True}))
    return out
