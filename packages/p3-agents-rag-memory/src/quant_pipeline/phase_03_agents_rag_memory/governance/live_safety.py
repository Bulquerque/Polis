"""Hard, fail-closed controls for production LIVE qualification.

All controls use only the Python standard library and Pydantic.  Vendor adapters
must pass resolved endpoints, evidence and artifact resolvers through these gates.
"""
from __future__ import annotations

import hashlib, hmac, ipaddress, json, os, re, socket, sqlite3, tempfile, time, threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DB_INIT_LOCK=threading.Lock()


def canonical_hash(value: object) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()
    return hashlib.sha256(raw).hexdigest()

class StrictModel(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True,validate_default=True)

class EgressPolicy(StrictModel):
    policy_version:str="p3.egress.v2"
    allowed_schemes:tuple[str,...]=("https",)
    allowed_hosts:tuple[str,...]
    allowed_ports:tuple[int,...]=(443,)
    allow_subdomains:bool=False
    forbid_private_networks:bool=True
    forbid_url_credentials:bool=True
    resolve_dns:bool=False
    # Local providers are opt-in.  This is intentionally separate from
    # ``forbid_private_networks`` so the default policy remains fail-closed.
    allow_local_endpoints:bool=False
    local_hosts:tuple[str,...]=("localhost", "localhost.localdomain", "127.0.0.1", "::1")
    max_redirects:int=Field(default=3,ge=0,le=10)
    metadata_addresses:tuple[str,...]=("169.254.169.254","100.100.100.200")
    @field_validator("allowed_hosts")
    @classmethod
    def hosts_nonempty(cls,v):
        out=tuple(sorted({x.lower().strip('.') for x in v if x.strip('.')}))
        if not out: raise ValueError("allowed_hosts cannot be empty")
        return out

class EndpointDecision(StrictModel):
    allowed:bool
    reason_codes:tuple[str,...]
    scheme:str|None=None
    host:str|None=None
    port:int|None=None
    resolved_addresses:tuple[str,...]=()
    endpoint_hash:str

def _host_allowed(host:str,p:EgressPolicy)->bool:
    return host in p.allowed_hosts or (p.allow_subdomains and any(host.endswith('.'+x) for x in p.allowed_hosts))

def _special(addr:ipaddress._BaseAddress,p:EgressPolicy)->bool:
    if str(addr) in p.metadata_addresses: return True
    return any((addr.is_private,addr.is_loopback,addr.is_link_local,addr.is_reserved,addr.is_multicast,addr.is_unspecified))

def default_dns_resolver(host:str,port:int)->tuple[str,...]:
    values={row[4][0] for row in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    return tuple(sorted(values))

def validate_endpoint(url:str,policy:EgressPolicy,resolver:Callable[[str,int],Sequence[str]]|None=None)->EndpointDecision:
    reasons=[]
    try: parsed=urlsplit(url)
    except ValueError: parsed=None; reasons.append("URL_PARSE_FAILED")
    if parsed is None:
        return EndpointDecision(allowed=False,reason_codes=tuple(reasons),endpoint_hash=canonical_hash(url))
    scheme=parsed.scheme.lower(); host=(parsed.hostname or '').lower().strip('.'); port=parsed.port or (443 if scheme=='https' else 80)
    if scheme not in policy.allowed_schemes: reasons.append("SCHEME_NOT_ALLOWED")
    if not host: reasons.append("HOST_MISSING")
    elif not _host_allowed(host,policy): reasons.append("HOST_NOT_ALLOWLISTED")
    if port not in policy.allowed_ports: reasons.append("PORT_NOT_ALLOWED")
    if policy.forbid_url_credentials and (parsed.username is not None or parsed.password is not None): reasons.append("URL_CREDENTIALS_FORBIDDEN")
    local_allowed = policy.allow_local_endpoints and host in policy.local_hosts
    if host in {"localhost","localhost.localdomain","127.0.0.1","::1"} and not local_allowed:
        reasons.append("LOCALHOST_FORBIDDEN")
    resolved=[]
    try:
        literal=ipaddress.ip_address(host)
        resolved=[str(literal)]
    except ValueError:
        if policy.resolve_dns and host:
            try: resolved=list((resolver or default_dns_resolver)(host,port))
            except Exception: reasons.append("DNS_RESOLUTION_FAILED")
    for item in resolved:
        try: addr=ipaddress.ip_address(item)
        except ValueError: reasons.append("DNS_RETURNED_INVALID_ADDRESS"); continue
        if policy.forbid_private_networks and not local_allowed and _special(addr,policy): reasons.append("PRIVATE_OR_SPECIAL_NETWORK_FORBIDDEN")
    if policy.resolve_dns and host and not resolved and "DNS_RESOLUTION_FAILED" not in reasons: reasons.append("DNS_EMPTY_ANSWER")
    return EndpointDecision(allowed=not reasons,reason_codes=tuple(sorted(set(reasons))),scheme=scheme or None,host=host or None,port=port,resolved_addresses=tuple(sorted(set(resolved))),endpoint_hash=canonical_hash({"url":url,"policy":policy.model_dump(mode='json'),"resolved":resolved}))

def validate_redirect_chain(urls:Sequence[str],policy:EgressPolicy,resolver=None)->tuple[EndpointDecision,...]:
    if not urls: raise ValueError("redirect chain cannot be empty")
    if len(urls)-1>policy.max_redirects: raise ValueError("redirect limit exceeded")
    decisions=tuple(validate_endpoint(url,policy,resolver) for url in urls)
    if not all(x.allowed for x in decisions): raise ValueError("redirect chain contains forbidden endpoint")
    return decisions

class CircuitState(StrEnum): CLOSED="CLOSED"; OPEN="OPEN"; HALF_OPEN="HALF_OPEN"
class CircuitBreakerPolicy(StrictModel):
    failure_threshold:int=Field(default=3,ge=1,le=100)
    recovery_timeout_seconds:float=Field(default=30,gt=0,le=3600)
    half_open_success_threshold:int=Field(default=1,ge=1,le=20)
@dataclass(slots=True)
class CircuitBreaker:
    policy:CircuitBreakerPolicy; state:CircuitState=CircuitState.CLOSED; failure_count:int=0; half_open_successes:int=0; opened_at:float|None=None
    def allow(self,now:float)->bool:
        if self.state is CircuitState.OPEN:
            if self.opened_at is None or now-self.opened_at<self.policy.recovery_timeout_seconds:return False
            self.state=CircuitState.HALF_OPEN; self.half_open_successes=0
        return True
    def record_success(self):
        if self.state is CircuitState.HALF_OPEN:
            self.half_open_successes+=1
            if self.half_open_successes>=self.policy.half_open_success_threshold:self.state=CircuitState.CLOSED;self.failure_count=0;self.opened_at=None
        else:self.failure_count=0
    def record_failure(self,now:float):
        self.failure_count+=1
        if self.state is CircuitState.HALF_OPEN or self.failure_count>=self.policy.failure_threshold:self.state=CircuitState.OPEN;self.opened_at=now;self.half_open_successes=0

class PersistentCircuitBreaker:
    def __init__(self,path:Path,provider_id:str,policy:CircuitBreakerPolicy):
        self.path=path;self.provider_id=provider_id;self.policy=policy;self._init()
    def _connect(self):
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None);c.execute('PRAGMA busy_timeout=10000');return c
    def _init(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with _DB_INIT_LOCK:
            with self._connect() as c:
                c.execute('PRAGMA journal_mode=WAL')
                c.execute('CREATE TABLE IF NOT EXISTS circuit(provider_id TEXT PRIMARY KEY,state TEXT NOT NULL,failure_count INTEGER NOT NULL,half_open_successes INTEGER NOT NULL,opened_at REAL,updated_at REAL NOT NULL)')
    def _load(self,c):
        row=c.execute('SELECT state,failure_count,half_open_successes,opened_at FROM circuit WHERE provider_id=?',(self.provider_id,)).fetchone()
        return CircuitBreaker(self.policy,*( [CircuitState(row[0]),row[1],row[2],row[3]] if row else []))
    def _save(self,c,b):
        c.execute('INSERT INTO circuit VALUES(?,?,?,?,?,?) ON CONFLICT(provider_id) DO UPDATE SET state=excluded.state,failure_count=excluded.failure_count,half_open_successes=excluded.half_open_successes,opened_at=excluded.opened_at,updated_at=excluded.updated_at',(self.provider_id,b.state.value,b.failure_count,b.half_open_successes,b.opened_at,time.time()))
    def allow(self,now:float)->bool:
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE');b=self._load(c);ok=b.allow(now);self._save(c,b);c.commit();return ok
    def record_success(self):
        with self._connect() as c:c.execute('BEGIN IMMEDIATE');b=self._load(c);b.record_success();self._save(c,b);c.commit()
    def record_failure(self,now:float):
        with self._connect() as c:c.execute('BEGIN IMMEDIATE');b=self._load(c);b.record_failure(now);self._save(c,b);c.commit()

class SecuritySeverity(StrEnum): INFO="INFO"; WARNING="WARNING"; BLOCK="BLOCK"
class SecurityFinding(StrictModel): code:str;severity:SecuritySeverity;path:str;excerpt_hash:str
class ContentSecurityReport(StrictModel): blocked:bool;findings:tuple[SecurityFinding,...];content_hash:str;scanner_version:str="p3.untrusted-content.v2"
_PATTERNS=(
("PROMPT_INJECTION_IGNORE",re.compile(r"\b(ignore|disregard)\b.{0,60}\b(previous|system|developer|instructions?)\b",re.I|re.S)),
("PROMPT_INJECTION_ROLE",re.compile(r"\b(system prompt|developer message|you are now|act as)\b",re.I)),
("TOOL_OUTPUT_INSTRUCTION",re.compile(r"\b(call|invoke|execute|run)\b.{0,40}\b(tool|command|shell|function)\b",re.I|re.S)),
("SECRET_MATERIAL",re.compile(r"\b(api[_ -]?key|secret|password|private[_ -]?key|bearer\s+[a-z0-9._-]+)\b",re.I)),)
def _walk(value,path='$'):
    if isinstance(value,str):yield path,value
    elif isinstance(value,Mapping):
        for k,v in value.items():yield from _walk(v,f'{path}.{k}')
    elif isinstance(value,(list,tuple)):
        for i,v in enumerate(value):yield from _walk(v,f'{path}[{i}]')
def scan_untrusted_content(value:object)->ContentSecurityReport:
    findings=[]
    for path,text in _walk(value):
        for code,pat in _PATTERNS:
            m=pat.search(text)
            if m: findings.append(SecurityFinding(code=code,severity=SecuritySeverity.BLOCK,path=path,excerpt_hash=canonical_hash(m.group(0))))
    findings.sort(key=lambda x:(x.path,x.code))
    return ContentSecurityReport(blocked=bool(findings),findings=tuple(findings),content_hash=canonical_hash(value))
def render_untrusted_text(text:str,*,source_id:str)->str:
    return f'<UNTRUSTED_EVIDENCE source_id="{source_id}">\n{text.replace("</UNTRUSTED_EVIDENCE>","&lt;/UNTRUSTED_EVIDENCE&gt;")}\n</UNTRUSTED_EVIDENCE>'

class AuditChainEntry(StrictModel): sequence:int=Field(ge=0);record_hash:str=Field(pattern=r'^[0-9a-f]{64}$');previous_hash:str|None=None;chain_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
def build_audit_chain(records):
    out=[];prev=None
    for seq,record in enumerate(records):
        payload=record.model_dump(mode='json',exclude_none=True) if hasattr(record,'model_dump') else record
        rh=canonical_hash(payload);ch=canonical_hash({'sequence':seq,'record_hash':rh,'previous_hash':prev});out.append(AuditChainEntry(sequence=seq,record_hash=rh,previous_hash=prev,chain_hash=ch));prev=ch
    return tuple(out)
def verify_audit_chain(records,chain)->bool:return build_audit_chain(records)==tuple(chain)
class SignedAuditEntry(AuditChainEntry): key_id:str;signature:str=Field(pattern=r'^[0-9a-f]{64}$')
def build_signed_audit_chain(records,*,key:bytes,key_id:str):
    return tuple(SignedAuditEntry(**e.model_dump(),key_id=key_id,signature=hmac.new(key,e.chain_hash.encode(),hashlib.sha256).hexdigest()) for e in build_audit_chain(records))
def verify_signed_audit_chain(records,chain,*,key:bytes,key_id:str)->bool:
    base=build_audit_chain(records);chain=tuple(chain)
    if len(base)!=len(chain):return False
    return all(c.key_id==key_id and c.sequence==b.sequence and c.record_hash==b.record_hash and c.previous_hash==b.previous_hash and c.chain_hash==b.chain_hash and hmac.compare_digest(c.signature,hmac.new(key,b.chain_hash.encode(),hashlib.sha256).hexdigest()) for b,c in zip(base,chain))

class ExactlyOnceDecision(StrEnum): ACCEPTED="ACCEPTED";DUPLICATE_SAME_PAYLOAD="DUPLICATE_SAME_PAYLOAD";DUPLICATE_CONFLICT="DUPLICATE_CONFLICT"
class ExactlyOnceResult(StrictModel): decision:ExactlyOnceDecision;idempotency_key:str;payload_hash:str;ledger_hash:str
class ExactlyOnceLedger:
    """Transactional SQLite ledger safe for concurrent local processes."""
    def __init__(self,path:Path):self.path=path.resolve();self.path.parent.mkdir(parents=True,exist_ok=True);self._init()
    def _connect(self):
        c=sqlite3.connect(self.path,timeout=15,isolation_level=None);c.execute('PRAGMA busy_timeout=15000');return c
    def _init(self):
        with _DB_INIT_LOCK:
            # `_DB_INIT_LOCK` only coordinates threads in this interpreter;
            # separate worker processes can still initialize the same ledger
            # simultaneously.  SQLite can reject the WAL mode transition in
            # that narrow startup window, so retry only the transient lock.
            for attempt in range(12):
                try:
                    with self._connect() as c:
                        c.execute('PRAGMA journal_mode=WAL')
                        c.execute('PRAGMA synchronous=FULL')
                        c.execute('CREATE TABLE IF NOT EXISTS ledger(idempotency_key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,created_at REAL NOT NULL)')
                    return
                except sqlite3.OperationalError as exc:
                    if 'locked' not in str(exc).lower() or attempt == 11:
                        raise
                    time.sleep(min(0.05 * (2 ** attempt), 1.0))
    def admit(self,idempotency_key:str,payload:object)->ExactlyOnceResult:
        ph=canonical_hash(payload)
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT payload_hash FROM ledger WHERE idempotency_key=?',(idempotency_key,)).fetchone()
            if row is None:c.execute('INSERT INTO ledger VALUES(?,?,?)',(idempotency_key,ph,time.time()));decision=ExactlyOnceDecision.ACCEPTED
            elif row[0]==ph:decision=ExactlyOnceDecision.DUPLICATE_SAME_PAYLOAD
            else:decision=ExactlyOnceDecision.DUPLICATE_CONFLICT
            rows=c.execute('SELECT idempotency_key,payload_hash FROM ledger ORDER BY idempotency_key').fetchall();c.commit()
        return ExactlyOnceResult(decision=decision,idempotency_key=idempotency_key,payload_hash=ph,ledger_hash=canonical_hash(rows))

class CheckpointSeal(StrictModel): checkpoint_hash:str;required_reference_hash:str;seal_hash:str;required_references:tuple[str,...];status:str
CHECKPOINT_REQUIRED_REFERENCES=("person_state_ref","belief_state_ref","memory_state_ref","social_graph_ref","endogenous_stimulus_queue_ref","belief_commitment_log_ref","run_snapshot_ref","foundation_manifest_ref","config_manifest_ref","prompt_manifest_ref","model_registry_ref","provider_fingerprint_ref","tool_registry_ref","entitlement_ref","rag_index_ref","graph_index_ref","memory_index_ref","replay_cache_ref")
def seal_checkpoint(value:Mapping[str,object])->CheckpointSeal:
    missing=[k for k in CHECKPOINT_REQUIRED_REFERENCES if not value.get(k)]
    if missing:raise ValueError(f'checkpoint missing replay-critical references: {missing}')
    ch=canonical_hash({k:v for k,v in value.items() if k!='content_hash'})
    if value.get('content_hash') not in (None,ch):raise ValueError('checkpoint content hash mismatch')
    rh=canonical_hash({k:value[k] for k in CHECKPOINT_REQUIRED_REFERENCES})
    return CheckpointSeal(checkpoint_hash=ch,required_reference_hash=rh,seal_hash=canonical_hash({'checkpoint_hash':ch,'reference_hash':rh}),required_references=CHECKPOINT_REQUIRED_REFERENCES,status='PASS')
class ArtifactResolver(Protocol):
    def __call__(self,reference:object)->object:...
def validate_checkpoint_references(value:Mapping[str,object],resolver:ArtifactResolver)->dict[str,str]:
    seal_checkpoint(value);out={}
    for key in CHECKPOINT_REQUIRED_REFERENCES:
        ref=value[key];payload=resolver(ref)
        if payload is None:raise ValueError(f'unresolved checkpoint reference: {key}')
        expected=ref.get('content_hash') if isinstance(ref,Mapping) else None
        observed=canonical_hash(payload)
        if expected and expected!=observed:raise ValueError(f'checkpoint reference hash mismatch: {key}')
        out[key]=observed
    return out

class LiveProbeStatus(StrEnum): PASS="PASS";FAIL="FAIL";TIMEOUT="TIMEOUT"
class LiveProbeEvidence(StrictModel):
    provider_id:str;status:LiveProbeStatus;endpoint_decision:EndpointDecision;request_hash:str;response_hash:str|None=None;schema_valid:bool;available_at_present:bool;provider_fingerprint:str;reason_codes:tuple[str,...]
async def qualify_provider_probe(*,provider_id:str,endpoint_url:str,egress_policy:EgressPolicy,probe:Callable[[],Any],response_validator:Callable[[object],bool],provider_version:str,timeout_seconds:float=10,resolver=None):
    import asyncio
    endpoint=validate_endpoint(endpoint_url,egress_policy,resolver);req=canonical_hash({'provider_id':provider_id,'endpoint':endpoint.endpoint_hash,'version':provider_version});fp=canonical_hash({'provider_id':provider_id,'endpoint':endpoint_url,'version':provider_version})
    if not endpoint.allowed:return LiveProbeEvidence(provider_id=provider_id,status=LiveProbeStatus.FAIL,endpoint_decision=endpoint,request_hash=req,schema_valid=False,available_at_present=False,provider_fingerprint=fp,reason_codes=endpoint.reason_codes)
    try:
        async with asyncio.timeout(timeout_seconds):value=await probe()
    except TimeoutError:return LiveProbeEvidence(provider_id=provider_id,status=LiveProbeStatus.TIMEOUT,endpoint_decision=endpoint,request_hash=req,schema_valid=False,available_at_present=False,provider_fingerprint=fp,reason_codes=('PROBE_TIMEOUT',))
    except Exception as exc:return LiveProbeEvidence(provider_id=provider_id,status=LiveProbeStatus.FAIL,endpoint_decision=endpoint,request_hash=req,schema_valid=False,available_at_present=False,provider_fingerprint=fp,reason_codes=(f'PROBE_ERROR:{type(exc).__name__}',))
    valid=bool(response_validator(value));available=isinstance(value,Mapping) and bool(value.get('available_at'))
    return LiveProbeEvidence(provider_id=provider_id,status=LiveProbeStatus.PASS if valid and available else LiveProbeStatus.FAIL,endpoint_decision=endpoint,request_hash=req,response_hash=canonical_hash(value),schema_valid=valid,available_at_present=available,provider_fingerprint=fp,reason_codes=() if valid and available else tuple(x for x,flag in [('RESPONSE_SCHEMA_INVALID',valid),('AVAILABLE_AT_MISSING',available)] if not flag))
