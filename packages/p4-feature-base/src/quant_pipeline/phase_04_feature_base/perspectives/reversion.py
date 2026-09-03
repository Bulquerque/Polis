from __future__ import annotations
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
from .series_ops import rolling_sum,robust_zscore
SUPPORTED_OBSERVERS={"reversion.short_term","reversion.robust_deviation","reversion.residual"}

def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        window=int(spec.parameters.get("window",5)); feature=spec.source_feature_ids[0]
        for entity in idx.entities(feature):
            source=idx.series(entity,feature)
            if spec.observer_id=="reversion.robust_deviation":
                path=source.fillna(0).cumsum(); values=robust_zscore(path,window).mul(-1); count=window*2-1
            else:
                values=rolling_sum(source,window).mul(-1); count=window
            for dt,val in values.items():
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements={feature:count})
                if prov is None: continue
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=None if pd.isna(val) else val,unit="reversion_pressure",sign_convention="HIGHER_MEANS_STRONGER_REVERSION_PRESSURE",provenance=prov,attributes={"window":window}))
    return out
