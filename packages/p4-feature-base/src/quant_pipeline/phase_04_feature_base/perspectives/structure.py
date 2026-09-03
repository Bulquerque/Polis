from __future__ import annotations
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
SUPPORTED_OBSERVERS={"structure.systematic_exposure","structure.common_mode_proxy","structure.contagion_pressure_proxy"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        a,b=spec.source_feature_ids[:2]
        for entity in idx.entities(a):
            sa,sb=idx.series(entity,a),idx.series(entity,b)
            for dt in sa.index.union(sb.index):
                va,vb=sa.get(dt,float("nan")),sb.get(dt,float("nan"))
                if pd.isna(va) or pd.isna(vb): continue
                if spec.observer_id=="structure.systematic_exposure": value=float(va)*float(vb)
                elif spec.observer_id=="structure.common_mode_proxy": value=abs(float(va))/(1+abs(float(vb)))
                else: value=abs(float(va))*max(float(vb),0)
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements={a:1,b:1})
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=value,unit="structure_state",sign_convention="HIGHER_MEANS_GREATER_SYSTEMATIC_OR_CONTAGION_PRESSURE",provenance=prov,attributes={"calculation_method":"PROXY" if "proxy" in spec.observer_id else "DIRECT_COMPOSITE"}))
    return out
