from __future__ import annotations
import numpy as np
import pandas as pd
from ..atomic_inputs import AtomicRecordIndex
from ..perspective_models import PerspectiveFeatureRecord,PerspectiveSpec
from ..perspective_records import one_perspective
from .series_ops import rolling_sum

SUPPORTED_OBSERVERS={"momentum.time_series","momentum.cross_sectional_rank","momentum.residual","momentum.volume_confirmed"}


def compute(records:tuple,specs:tuple[PerspectiveSpec,...]) -> list[PerspectiveFeatureRecord]:
    idx=AtomicRecordIndex(records); out=[]
    for spec in specs:
        window=int(spec.parameters.get("window",21))
        base=spec.source_feature_ids[0]
        entities=[e for e in idx.entities(base) if e not in set(spec.parameters.get("exclude_entities",["BENCHMARK"]))]
        if spec.observer_id=="momentum.cross_sectional_rank":
            values={e:rolling_sum(idx.series(e,base),window) for e in entities}
            dates=sorted(set().union(*(s.index for s in values.values()))) if values else []
            for dt in dates:
                current={e:float(s.loc[dt]) for e,s in values.items() if dt in s.index and pd.notna(s.loc[dt])}
                if len(current)<2: continue
                ranks=pd.Series(current).rank(method="average",pct=True).mul(2).sub(1)
                prov=idx.collect_many([(e,base,window) for e in sorted(current)],dt)
                if prov is None: continue
                for e,val in ranks.items(): out.append(one_perspective(decision_time=dt,entity_id=e,spec=spec,value=val,unit="cross_sectional_rank",sign_convention="HIGHER_MEANS_STRONGER_RELATIVE_MOMENTUM",provenance=prov,attributes={"window":window,"universe_size":len(current)}))
            continue
        for entity in entities:
            series=idx.series(entity,base)
            values=rolling_sum(series,window)
            requirements={base:window}
            if spec.observer_id=="momentum.volume_confirmed":
                volume_id=spec.source_feature_ids[1]; volume=idx.series(entity,volume_id)
                values=values.mul(volume.reindex(values.index).clip(lower=0,upper=float(spec.parameters.get("volume_cap",3.0))))
                requirements[volume_id]=1
            for dt,val in values.items():
                prov=idx.collect(entity_id=entity,decision_time=dt,requirements=requirements)
                if prov is None: continue
                convention="HIGHER_MEANS_STRONGER_PERSISTENCE"
                out.append(one_perspective(decision_time=dt,entity_id=entity,spec=spec,value=None if pd.isna(val) else val,unit="return_state",sign_convention=convention,provenance=prov,attributes={"window":window}))
    return out
