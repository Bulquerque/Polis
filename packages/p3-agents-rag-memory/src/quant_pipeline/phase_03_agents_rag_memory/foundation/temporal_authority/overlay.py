from __future__ import annotations
from datetime import datetime
from typing import Any, Mapping
from .canonical import parse_aware_datetime
from .errors import S2ContractError

REQUIREMENTS={
 'clean_context_source_panel':('available_at','ingested_at'),
 'clean_document_panel':('effective_time','available_at','ingested_at'),
 'clean_event_reference_panel':('effective_time','available_at','ingested_at'),
 'source_quality_panel':('available_at','ingested_at'),
}
ALIASES={'available_at':('available_at','declared_available_at','created_at'),'ingested_at':('ingested_at','created_at'),'effective_time':('effective_time','event_time','reference_date')}
def _get(row:Mapping[str,Any],artifact:Mapping[str,Any],field:str):
    for name in ALIASES[field]:
        value=row.get(name,artifact.get(name))
        if value not in (None,''):return value
    return None
def normalize_temporal_artifact(artifact_name:str,artifact:Mapping[str,Any],*,as_of_time:str)->dict[str,Any]:
    cutoff=parse_aware_datetime(as_of_time,field='as_of_time');records=artifact.get('records',artifact.get('items',[]))
    if not isinstance(records,list):raise S2ContractError('P3_TEMPORAL_RECORDS_INVALID',artifact_name)
    out=[]
    for index,row in enumerate(records):
        if not isinstance(row,Mapping):raise S2ContractError('P3_TEMPORAL_RECORD_INVALID',f'{artifact_name}[{index}]')
        item=dict(row)
        for field in REQUIREMENTS.get(artifact_name,()):
            value=_get(row,artifact,field)
            if value in (None,''):raise S2ContractError('P3_TEMPORAL_FIELD_MISSING',f'{artifact_name}[{index}].{field}')
            parsed=parse_aware_datetime(str(value) if len(str(value))!=10 else str(value)+'T00:00:00Z',field=field)
            if field=='available_at' and parsed>cutoff:raise S2ContractError('P3_TEMPORAL_FUTURE_RECORD',f'{artifact_name}[{index}]')
            item[field]=parsed.isoformat().replace('+00:00','Z')
        if item.get('ingested_at') and item.get('available_at') and parse_aware_datetime(item['ingested_at'],field='ingested_at')<parse_aware_datetime(item['available_at'],field='available_at'):
            raise S2ContractError('P3_TEMPORAL_INGESTED_BEFORE_AVAILABLE',f'{artifact_name}[{index}]')
        out.append(item)
    result=dict(artifact);result['records']=out;result['as_of_time']=cutoff.isoformat().replace('+00:00','Z');result['temporal_overlay_version']='p3.temporal-overlay.v1';return result
