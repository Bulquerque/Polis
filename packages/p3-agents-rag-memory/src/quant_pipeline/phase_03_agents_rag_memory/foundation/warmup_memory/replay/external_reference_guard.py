from __future__ import annotations
from datetime import datetime,timezone
from typing import Any

class ExternalReferenceLeakageError(ValueError): pass

def _dt(value:Any)->datetime:
    if isinstance(value,datetime): observed=value
    else: observed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if observed.tzinfo is None: raise ExternalReferenceLeakageError('timestamp must be timezone-aware')
    return observed.astimezone(timezone.utc)

def validate_external_references(*,as_of_time:Any,provider_snapshots:list[dict[str,Any]],document_refs:list[dict[str,Any]],tool_results:list[dict[str,Any]])->dict[str,Any]:
    cutoff=_dt(as_of_time); issues=[]; checked=0
    for kind,rows,field,id_field in [
      ('provider',provider_snapshots,'snapshot_available_at','provider_id'),
      ('document',document_refs,'available_at','document_id'),
      ('tool_result',tool_results,'available_at','tool_call_id'),
    ]:
      for row in rows:
        checked+=1
        if field not in row: issues.append(f'{kind}:missing_{field}:{row.get(id_field,"unknown")}'); continue
        if _dt(row[field])>cutoff: issues.append(f'{kind}:future:{row.get(id_field,"unknown")}')
    if issues: raise ExternalReferenceLeakageError(';'.join(issues))
    return {'status':'PASS','checked_reference_count':checked,'as_of_time':cutoff.isoformat().replace('+00:00','Z')}
