from __future__ import annotations
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from typing import Any

class CalendarPolicyError(ValueError): pass

def normalize_to_utc(value:datetime,timezone_name:str)->datetime:
    try: zone=ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc: raise CalendarPolicyError(f"unsupported timezone:{timezone_name}") from exc
    if value.tzinfo is None: value=value.replace(tzinfo=zone,fold=0)
    return value.astimezone(timezone.utc)

def is_business_day(value:date,*,holiday_dates:set[date])->bool:
    return value.weekday()<5 and value not in holiday_dates

def validate_calendar_policy(policy:dict[str,Any])->dict[str,Any]:
    supported=policy.get("supported_timezones",[])
    if "UTC" not in supported or len(supported)!=len(set(supported)): raise CalendarPolicyError("timezone registry invalid")
    for name in supported:
        try: ZoneInfo(name)
        except ZoneInfoNotFoundError as exc: raise CalendarPolicyError(f"timezone unavailable:{name}") from exc
    for cal,rows in policy.get("holiday_calendars",{}).items():
        parsed=[date.fromisoformat(x) for x in rows]
        if len(parsed)!=len(set(parsed)): raise CalendarPolicyError(f"duplicate holiday:{cal}")
    return {"status":"PASS","timezone_count":len(supported),"calendar_count":len(policy.get("holiday_calendars",{}))}
