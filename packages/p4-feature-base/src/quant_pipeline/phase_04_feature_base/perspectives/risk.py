from __future__ import annotations
import math
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"risk.multiscale","risk.downside","risk.drawdown_stress","risk.implied_uncertainty"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        a,b=(spec.source_feature_ids+("",))[:2]
        for entity in idx.entities(a):
            sa=idx.series(entity,a); sb=idx.series(entity,b) if b else pd.Series(dtype=float)
            dates=sa.index if not b else sa.index.union(sb.index)
            for dt in dates:
                va=sa.get(dt,float("nan")); vb=sb.get(dt,float("nan")) if b else float("nan")
                req={a:1}; value=None
                if spec.observer_id=="risk.multiscale" and pd.notna(va) and pd.notna(vb) and va>=0 and vb>=0:
                    value=math.sqrt(float(va)*float(vb)); req[b]=1
                elif spec.observer_id=="risk.downside" and pd.notna(va): value=float(va)
                elif spec.observer_id=="risk.drawdown_stress" and pd.notna(va) and pd.notna(vb):
                    value=abs(float(va))*(1+math.log1p(max(float(vb),0))); req[b]=1
                elif spec.observer_id=="risk.implied_uncertainty" and pd.notna(va) and pd.notna(vb):
                    value=math.sqrt(float(va)**2+float(vb)**2); req[b]=1
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements=req)
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="risk_state",sign_convention="HIGHER_MEANS_GREATER_RISK_OR_UNCERTAINTY",provenance=prov,attributes={"composite":spec.observer_id}))
    return out
