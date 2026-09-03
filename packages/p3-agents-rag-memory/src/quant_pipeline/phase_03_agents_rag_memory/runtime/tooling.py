from __future__ import annotations

import asyncio
from collections.abc import Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ..governance.live_safety import build_audit_chain, scan_untrusted_content, verify_audit_chain
from ..runtime_shared.s21_errors import S21ContractError, S21DependencyError
from ..runtime_shared.s21_hashing import content_hash, stable_id
from ..runtime_shared.s21_models import (
    ArtifactStatus,
    FORBIDDEN_FIELDS,
    LineageRecord,
    MCPGatewayPolicy,
    PersonToolEntitlementPanel,
    PersonToolEntitlementRecord,
    Phase3RunSnapshot,
    ProviderAdapterRegistryConfig,
    RawToolResultPanel,
    RawToolResultRecord,
    RequestValidationStatus,
    RetrievalEvidenceMap,
    ToolCallAuditContract,
    ToolCallAuditPanel,
    ToolCallAuditRecord,
    ToolCallRequestPanel,
    ToolDiscoveryEventPanel,
    ToolDiscoveryEventRecord,
    ToolErrorRecord,
    ToolExecutionResponse,
    ToolOperationEntitlement,
    ToolExecutionStatus,
    ToolResultValidationStatus,
    ValidatedToolCallRequestPanel,
    ValidatedToolCallRequestRecord,
    ValidatedToolResultPanel,
    ValidatedToolResultRecord,
)
from ..runtime_shared.s21_ports import S21Runtime


def _contains_secret(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_FIELDS:
                return True
            if _contains_secret(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    return False


def _lineage(module_id: str, *lineages: LineageRecord) -> LineageRecord:
    source_ids = tuple(sorted({item.lineage_id for item in lineages}))
    source_hashes = {
        item.lineage_id: content_hash(item.model_dump(mode="json"))
        for item in lineages
    }
    return LineageRecord(
        lineage_id=stable_id("lin", module_id, source_ids, source_hashes),
        source_artifact_ids=source_ids,
        source_hashes=source_hashes,
        producer_module_id=module_id,
    )



def _find_operation(
    entitlement: PersonToolEntitlementRecord | None,
    operation_id: str,
) -> ToolOperationEntitlement | None:
    if entitlement is None:
        return None
    return next(
        (item for item in entitlement.operations if item.operation_id == operation_id),
        None,
    )


def _initial_request_status(
    *,
    request,
    entitlement: PersonToolEntitlementRecord | None,
    operation: ToolOperationEntitlement | None,
    gateway_policy: MCPGatewayPolicy,
    seen_idempotency_keys: set[str],
    seen_request_ids: set[str],
) -> tuple[RequestValidationStatus, list[str]]:
    reasons: list[str] = []
    status = RequestValidationStatus.ACCEPTED
    if entitlement is None:
        return RequestValidationStatus.REJECTED_ENTITLEMENT, ["PERSON_NOT_ENTITLED"]
    if operation is None:
        return RequestValidationStatus.REJECTED_OPERATION, ["OPERATION_NOT_ENTITLED"]
    if _contains_secret(request.arguments):
        status = RequestValidationStatus.REJECTED_CREDENTIAL
        reasons.append("RAW_CREDENTIAL_FIELD")
    if (
        status == RequestValidationStatus.ACCEPTED
        and request.credential_handle is not None
        and request.credential_handle != entitlement.credential_handle
    ):
        status = RequestValidationStatus.REJECTED_CREDENTIAL
        reasons.append("CREDENTIAL_HANDLE_MISMATCH")
    if request.requested_at > request.as_of:
        status = RequestValidationStatus.REJECTED_TEMPORAL
        reasons.append("REQUESTED_AFTER_AS_OF")
    if (
        status == RequestValidationStatus.ACCEPTED
        and gateway_policy.pit_required
        and not operation.point_in_time_safe
    ):
        status = RequestValidationStatus.REJECTED_TEMPORAL
        reasons.append("OPERATION_NOT_POINT_IN_TIME_SAFE")
    if request.idempotency_key in seen_idempotency_keys:
        status = RequestValidationStatus.REJECTED_DUPLICATE
        reasons.append("DUPLICATE_IDEMPOTENCY_KEY")
    else:
        seen_idempotency_keys.add(request.idempotency_key)
    if request.tool_call_request_id in seen_request_ids:
        status = RequestValidationStatus.REJECTED_DUPLICATE
        reasons.append("DUPLICATE_TOOL_CALL_REQUEST_ID")
    else:
        seen_request_ids.add(request.tool_call_request_id)
    return status, reasons


def _effective_call_budget(
    entitlement: PersonToolEntitlementRecord,
    gateway_policy: MCPGatewayPolicy,
) -> int:
    return min(
        entitlement.budget_calls_per_cycle,
        gateway_policy.cognition_default_calls_per_person_cycle,
        gateway_policy.hard_limit_calls_per_person_cycle,
    )


def _schema_reason_codes(
    operation: ToolOperationEntitlement,
    arguments: Mapping[str, object],
) -> tuple[str, ...]:
    try:
        Draft202012Validator.check_schema(operation.arguments_schema)
        errors = sorted(
            Draft202012Validator(operation.arguments_schema).iter_errors(arguments),
            key=lambda item: list(item.path),
        )
    except SchemaError as exc:
        raise S21DependencyError(
            code="TOOL_ARGUMENT_SCHEMA_INVALID",
            message="entitlement contains an invalid JSON Schema",
            module_id="P3.S21.M02",
            details={"operation_id": operation.operation_id},
        ) from exc
    return tuple(
        f"ARGUMENT_SCHEMA:{error.json_path}:{error.message}" for error in errors
    )


def _validated_request_record(
    *,
    request,
    entitlement: PersonToolEntitlementRecord | None,
    operation: ToolOperationEntitlement | None,
    status: RequestValidationStatus,
    reasons: list[str],
) -> ValidatedToolCallRequestRecord:
    return ValidatedToolCallRequestRecord(
        request=request,
        validation_status=status,
        reason_codes=tuple(reasons),
        provider_id=entitlement.provider_id if entitlement else None,
        entitlement_version=entitlement.entitlement_version if entitlement else None,
        arguments_schema=operation.arguments_schema if operation else None,
        result_schema=operation.result_schema if operation else None,
        read_only=operation.read_only if operation else None,
        point_in_time_safe=operation.point_in_time_safe if operation else None,
    )


def validate_tool_requests(
    *,
    requests: ToolCallRequestPanel,
    entitlements: PersonToolEntitlementPanel,
    gateway_policy: MCPGatewayPolicy,
    audit_contract: ToolCallAuditContract,
) -> ValidatedToolCallRequestPanel:
    """Authorize requests deterministically against entitlement, PIT and budget."""
    del audit_contract
    module_id = "P3.S21.M02"
    entitlement_index = {
        (item.person_id, item.tool_id): item for item in entitlements.records
    }
    accepted_count: dict[str, int] = {}
    seen_keys: set[str] = set()
    seen_request_ids: set[str] = set()
    validated: list[ValidatedToolCallRequestRecord] = []

    for request in sorted(
        requests.records,
        key=lambda item: (item.person_id, item.requested_at, item.tool_call_request_id),
    ):
        entitlement = entitlement_index.get((request.person_id, request.tool_id))
        operation = _find_operation(entitlement, request.operation_id)
        status, reasons = _initial_request_status(
            request=request,
            entitlement=entitlement,
            operation=operation,
            gateway_policy=gateway_policy,
            seen_idempotency_keys=seen_keys,
            seen_request_ids=seen_request_ids,
        )
        if status == RequestValidationStatus.ACCEPTED and entitlement is not None:
            if accepted_count.get(request.person_id, 0) >= _effective_call_budget(
                entitlement, gateway_policy
            ):
                status = RequestValidationStatus.REJECTED_BUDGET
                reasons.append("EFFECTIVE_BUDGET_EXCEEDED")
        if status == RequestValidationStatus.ACCEPTED and operation is not None:
            schema_reasons = _schema_reason_codes(operation, request.arguments)
            if schema_reasons:
                status = RequestValidationStatus.REJECTED_SCHEMA
                reasons.extend(schema_reasons)
            else:
                accepted_count[request.person_id] = accepted_count.get(request.person_id, 0) + 1
        validated.append(
            _validated_request_record(
                request=request,
                entitlement=entitlement,
                operation=operation,
                status=status,
                reasons=reasons,
            )
        )

    has_rejections = any(
        item.validation_status != RequestValidationStatus.ACCEPTED for item in validated
    )
    status = (
        ArtifactStatus.EMPTY_VALID if not validated
        else ArtifactStatus.DEGRADED if has_rejections
        else ArtifactStatus.READY
    )
    return ValidatedToolCallRequestPanel(
        status=status,
        records=tuple(validated),
        lineage=_lineage(module_id, requests.lineage, entitlements.lineage),
        reason_code=(
            "NO_TOOL_REQUESTS" if not validated
            else "SOME_TOOL_REQUESTS_REJECTED" if has_rejections
            else None
        ),
    )


def _failed_response(
    *,
    provider_id: str,
    status: ToolExecutionStatus,
    code: str,
    message: str,
    retryable: bool,
) -> ToolExecutionResponse:
    return ToolExecutionResponse(
        status=status,
        provider_id=provider_id,
        error=ToolErrorRecord(code=code, message=message, retryable=retryable),
    )


async def _gateway_attempt(
    *,
    request: ValidatedToolCallRequestRecord,
    runtime: S21Runtime,
    gateway_policy: MCPGatewayPolicy,
    semaphore: asyncio.Semaphore,
) -> ToolExecutionResponse:
    provider_id = request.provider_id or ""
    try:
        async with semaphore:
            async with asyncio.timeout(gateway_policy.timeout_seconds):
                return await runtime.tool_gateway.execute(request)
    except TimeoutError as exc:
        return _failed_response(
            provider_id=provider_id,
            status=ToolExecutionStatus.FAILED_TIMEOUT,
            code="TIMEOUT",
            message=str(exc) or "tool timed out",
            retryable=True,
        )
    except PermissionError as exc:
        return _failed_response(
            provider_id=provider_id,
            status=ToolExecutionStatus.FAILED_AUTHENTICATION,
            code="AUTHENTICATION",
            message=str(exc),
            retryable=False,
        )
    except ConnectionError as exc:
        return _failed_response(
            provider_id=provider_id,
            status=ToolExecutionStatus.FAILED_PROVIDER,
            code="CONNECTION",
            message=str(exc),
            retryable=True,
        )


async def _execute_with_retry(
    *,
    request: ValidatedToolCallRequestRecord,
    runtime: S21Runtime,
    gateway_policy: MCPGatewayPolicy,
    semaphore: asyncio.Semaphore,
) -> tuple[ToolExecutionResponse, int]:
    retry_count = 0
    retry_allowed = bool(request.read_only) or bool(request.request.idempotency_key)
    response: ToolExecutionResponse | None = None
    for attempt in range(gateway_policy.max_retry_attempts + 1):
        response = await _gateway_attempt(
            request=request,
            runtime=runtime,
            gateway_policy=gateway_policy,
            semaphore=semaphore,
        )
        retryable = bool(response.error and response.error.retryable)
        if (
            response.status == ToolExecutionStatus.SUCCEEDED
            or not retryable
            or not retry_allowed
            or attempt >= gateway_policy.max_retry_attempts
        ):
            break
        retry_count += 1
        if gateway_policy.retry_backoff_seconds:
            await asyncio.sleep(
                gateway_policy.retry_backoff_seconds * (2 ** (retry_count - 1))
            )
    if response is None:
        raise S21DependencyError(
            code="TOOL_GATEWAY_RETURNED_NO_RESPONSE",
            message="tool gateway returned no response",
            module_id="P3.S21.M03",
        )
    return response, retry_count


def _execution_records(
    *,
    request: ValidatedToolCallRequestRecord,
    response: ToolExecutionResponse,
    retry_count: int,
    started_at,
    finished_at,
    latency_ms: float,
) -> tuple[RawToolResultRecord, ToolCallAuditRecord, ToolDiscoveryEventRecord]:
    provider_id = request.provider_id or ""
    execution_id = stable_id("exec", request.request.tool_call_request_id)
    if response.provider_id != provider_id:
        raise S21DependencyError(
            code="TOOL_PROVIDER_IDENTITY_MISMATCH",
            message="tool gateway response provider differs from the authorized provider",
            module_id="P3.S21.M03",
        )
    evidence_refs = response.evidence_refs
    if response.status == ToolExecutionStatus.SUCCEEDED and not evidence_refs:
        evidence_refs = (f"tool:{execution_id}",)
    raw_result = RawToolResultRecord(
        tool_call_request_id=request.request.tool_call_request_id,
        cognition_transaction_id=request.request.cognition_transaction_id,
        execution_id=execution_id,
        person_id=request.request.person_id,
        tool_id=request.request.tool_id,
        operation_id=request.request.operation_id,
        provider_id=provider_id,
        status=response.status,
        started_at=started_at,
        finished_at=finished_at,
        available_at=response.available_at,
        latency_ms=latency_ms,
        cost_units=response.cost_units,
        canonical_payload=response.canonical_payload,
        raw_payload_ref=response.raw_payload_ref,
        response_hash=response.response_hash,
        evidence_refs=evidence_refs,
        error=response.error,
        result_schema=request.result_schema,
    )
    audit = ToolCallAuditRecord(
        audit_id=stable_id("audit", execution_id),
        tool_call_request_id=request.request.tool_call_request_id,
        execution_id=execution_id,
        cognition_transaction_id=request.request.cognition_transaction_id,
        person_id=request.request.person_id,
        provider_id=provider_id,
        tool_id=request.request.tool_id,
        operation_id=request.request.operation_id,
        status=response.status,
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=latency_ms,
        cost_units=response.cost_units,
        retry_count=retry_count,
        request_hash=content_hash(request.request.model_dump(mode="json")),
        response_hash=response.response_hash,
        credential_handle_used=request.request.credential_handle is not None,
    )
    discovery = ToolDiscoveryEventRecord(
        event_id=stable_id("discovery", provider_id, request.request.tool_id, request.request.operation_id),
        cognition_transaction_id=request.request.cognition_transaction_id,
        person_id=request.request.person_id,
        provider_id=provider_id,
        tool_id=request.request.tool_id,
        operation_id=request.request.operation_id,
        discovered_at=started_at,
        status="DISCOVERED",
    )
    return raw_result, audit, discovery


async def _execute_one(
    *,
    request: ValidatedToolCallRequestRecord,
    runtime: S21Runtime,
    gateway_policy: MCPGatewayPolicy,
    semaphore: asyncio.Semaphore,
) -> tuple[RawToolResultRecord, ToolCallAuditRecord, ToolDiscoveryEventRecord]:
    if request.validation_status != RequestValidationStatus.ACCEPTED:
        raise S21ContractError(
            code="EXECUTION_OF_REJECTED_REQUEST",
            message="M03 received a rejected request for execution",
            module_id="P3.S21.M03",
        )
    if request.provider_id is None:
        raise S21ContractError(
            code="PROVIDER_ID_MISSING",
            message="accepted request has no provider ID",
            module_id="P3.S21.M03",
        )
    started_at = runtime.clock.now()
    started_monotonic = runtime.clock.monotonic()
    response, retry_count = await _execute_with_retry(
        request=request,
        runtime=runtime,
        gateway_policy=gateway_policy,
        semaphore=semaphore,
    )
    finished_at = runtime.clock.now()
    latency_ms = max(0.0, (runtime.clock.monotonic() - started_monotonic) * 1000.0)
    return _execution_records(
        request=request,
        response=response,
        retry_count=retry_count,
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=latency_ms,
    )


def _provider_semaphores(
    provider_registry: ProviderAdapterRegistryConfig,
) -> tuple[set[str], dict[str, asyncio.Semaphore]]:
    configs = {
        item.provider_id: item
        for item in provider_registry.tool_providers
        if item.enabled
    }
    provider_ids = set(configs)
    if not provider_ids:
        provider_ids = {item.provider_id for item in provider_registry.providers if item.enabled}
    semaphores = {
        provider_id: asyncio.Semaphore(configs[provider_id].max_concurrency)
        for provider_id in configs
    }
    if not configs:
        semaphores = {provider_id: asyncio.Semaphore(1) for provider_id in provider_ids}
    return provider_ids, semaphores


def _chain_audits(audits: list[ToolCallAuditRecord]) -> list[ToolCallAuditRecord]:
    base = [item.model_copy(update={"previous_audit_hash": None, "audit_hash": None}) for item in audits]
    chain = build_audit_chain(base)
    chained = [
        item.model_copy(update={"previous_audit_hash": link.previous_hash, "audit_hash": link.chain_hash})
        for item, link in zip(base, chain, strict=True)
    ]
    normalized = [item.model_copy(update={"previous_audit_hash": None, "audit_hash": None}) for item in chained]
    if not verify_audit_chain(normalized, chain):
        raise S21ContractError(code="AUDIT_CHAIN_INVALID", message="tool audit hash chain validation failed", module_id="P3.S21.M03")
    return chained


def _validate_audits(
    audits: list[ToolCallAuditRecord],
    audit_contract: ToolCallAuditContract,
) -> None:
    required = set(audit_contract.required_fields)
    for audit in audits:
        missing = required - set(audit.model_dump(mode="json"))
        if missing:
            raise S21ContractError(
                code="AUDIT_CONTRACT_MISMATCH",
                message="generated audit does not satisfy the declared audit contract",
                module_id="P3.S21.M03",
                details={"missing_fields": sorted(missing)},
            )


def _execution_output_panels(
    *,
    accepted: list[ValidatedToolCallRequestRecord],
    results: list[RawToolResultRecord],
    audits: list[ToolCallAuditRecord],
    discoveries: list[ToolDiscoveryEventRecord],
    lineage: LineageRecord,
) -> dict[str, object]:
    has_failure = any(item.status != ToolExecutionStatus.SUCCEEDED for item in results)
    status = (
        ArtifactStatus.EMPTY_VALID if not accepted
        else ArtifactStatus.DEGRADED if has_failure
        else ArtifactStatus.READY
    )
    return {
        "raw_tool_result_panel": RawToolResultPanel(
            status=status,
            records=tuple(results),
            lineage=lineage,
            reason_code=("NO_AUTHORIZED_TOOL_REQUESTS" if not accepted else "SOME_TOOL_EXECUTIONS_FAILED" if has_failure else None),
        ),
        "tool_call_audit_panel": ToolCallAuditPanel(
            status=status,
            records=tuple(audits),
            lineage=lineage,
            reason_code=("NO_TOOL_EXECUTIONS" if not audits else None),
        ),
        "tool_discovery_event_panel": ToolDiscoveryEventPanel(
            status=ArtifactStatus.READY if discoveries else ArtifactStatus.EMPTY_VALID,
            records=tuple(discoveries),
            lineage=lineage,
            reason_code=("NO_TOOL_DISCOVERY_EVENTS" if not discoveries else None),
        ),
    }


async def execute_tool_requests(
    *,
    validated_requests: ValidatedToolCallRequestPanel,
    gateway_policy: MCPGatewayPolicy,
    audit_contract: ToolCallAuditContract,
    provider_registry: ProviderAdapterRegistryConfig,
    runtime: S21Runtime,
) -> dict[str, object]:
    """Execute authorized tool calls with structured concurrency and audit."""
    provider_ids, semaphores = _provider_semaphores(provider_registry)
    accepted = [
        item for item in validated_requests.records
        if item.validation_status == RequestValidationStatus.ACCEPTED
    ]
    for item in accepted:
        if item.provider_id not in provider_ids:
            raise S21DependencyError(
                code="TOOL_PROVIDER_NOT_REGISTERED",
                message="authorized tool provider is absent from provider registry",
                module_id="P3.S21.M03",
                details={"provider_id": item.provider_id},
            )
    tasks = {}
    async with asyncio.TaskGroup() as group:
        for request in sorted(
            accepted,
            key=lambda item: (item.request.person_id, item.request.tool_call_request_id),
        ):
            tasks[request.request.tool_call_request_id] = group.create_task(
                _execute_one(
                    request=request,
                    runtime=runtime,
                    gateway_policy=gateway_policy,
                    semaphore=semaphores[request.provider_id or ""],
                )
            )
    results: list[RawToolResultRecord] = []
    audits: list[ToolCallAuditRecord] = []
    discoveries: list[ToolDiscoveryEventRecord] = []
    for request_id in sorted(tasks):
        result, audit, discovery = tasks[request_id].result()
        results.append(result)
        audits.append(audit)
        discoveries.append(discovery)
    audits = _chain_audits(audits)
    _validate_audits(audits, audit_contract)
    return _execution_output_panels(
        accepted=accepted,
        results=results,
        audits=audits,
        discoveries=discoveries,
        lineage=_lineage("P3.S21.M03", validated_requests.lineage),
    )


def _validate_result_record(
    *,
    result: RawToolResultRecord,
    audit: ToolCallAuditRecord | None,
    snapshot: Phase3RunSnapshot,
    known_evidence: set[str],
) -> ValidatedToolResultRecord:
    reasons: list[str] = []
    if audit is None or audit.tool_call_request_id != result.tool_call_request_id:
        status = ToolResultValidationStatus.INVALID_LINKAGE
        reasons.append("AUDIT_LINKAGE_MISSING")
    elif result.status != ToolExecutionStatus.SUCCEEDED:
        status = ToolResultValidationStatus.FAILURE_PRESERVED
        reasons.append(result.status.value)
    elif result.available_at is None or result.available_at > snapshot.as_of:
        status = ToolResultValidationStatus.INVALID_TEMPORAL
        reasons.append("AVAILABLE_AT_AFTER_AS_OF_OR_MISSING")
    elif not result.response_hash or not result.evidence_refs:
        status = ToolResultValidationStatus.INVALID_PROVENANCE
        reasons.append("RESPONSE_HASH_OR_EVIDENCE_MISSING")
    elif result.result_schema is None or result.canonical_payload is None:
        status = ToolResultValidationStatus.INVALID_SCHEMA
        reasons.append("RESULT_SCHEMA_OR_PAYLOAD_MISSING")
    else:
        try:
            Draft202012Validator.check_schema(result.result_schema)
            errors = sorted(
                Draft202012Validator(result.result_schema).iter_errors(result.canonical_payload),
                key=lambda item: list(item.path),
            )
        except SchemaError as exc:
            raise S21DependencyError(
                code="TOOL_RESULT_SCHEMA_INVALID",
                message="authorized tool result schema is invalid",
                module_id="P3.S21.M04",
            ) from exc
        if errors:
            status = ToolResultValidationStatus.INVALID_SCHEMA
            reasons.extend(f"RESULT_SCHEMA:{error.json_path}:{error.message}" for error in errors)
        else:
            security = scan_untrusted_content(result.canonical_payload)
            if security.blocked:
                status = ToolResultValidationStatus.INVALID_PROVENANCE
                reasons.extend(f"UNTRUSTED_CONTENT:{item.code}:{item.path}" for item in security.findings)
                return ValidatedToolResultRecord(
                    raw_result=result, validation_status=status, reason_codes=tuple(reasons), validated_payload=None
                )
            invalid = [
                ref for ref in result.evidence_refs
                if ref not in known_evidence and ref != f"tool:{result.execution_id}"
            ]
            if invalid:
                status = ToolResultValidationStatus.INVALID_EVIDENCE
                reasons.extend(f"UNKNOWN_EVIDENCE:{ref}" for ref in invalid)
            else:
                status = ToolResultValidationStatus.VALID
    return ValidatedToolResultRecord(
        raw_result=result,
        validation_status=status,
        reason_codes=tuple(reasons),
        validated_payload=result.canonical_payload if status == ToolResultValidationStatus.VALID else None,
    )


def validate_tool_results(
    *,
    raw_results: RawToolResultPanel,
    audit_panel: ToolCallAuditPanel,
    snapshot: Phase3RunSnapshot,
    retrieval_evidence: RetrievalEvidenceMap,
) -> ValidatedToolResultPanel:
    """Validate result schema, temporal safety, provenance and linkage."""
    module_id = "P3.S21.M04"
    audits = {item.execution_id: item for item in audit_panel.records}
    known_evidence = {item.evidence_id for item in retrieval_evidence.records}
    validated = [
        _validate_result_record(
            result=result,
            audit=audits.get(result.execution_id),
            snapshot=snapshot,
            known_evidence=known_evidence,
        )
        for result in sorted(raw_results.records, key=lambda item: item.execution_id)
    ]
    allowed = {
        ToolResultValidationStatus.VALID,
        ToolResultValidationStatus.FAILURE_PRESERVED,
    }
    has_invalid = any(item.validation_status not in allowed for item in validated)
    has_failure = any(
        item.validation_status == ToolResultValidationStatus.FAILURE_PRESERVED
        for item in validated
    )
    status = (
        ArtifactStatus.EMPTY_VALID if not validated
        else ArtifactStatus.DEGRADED if has_invalid or has_failure
        else ArtifactStatus.READY
    )
    return ValidatedToolResultPanel(
        status=status,
        records=tuple(validated),
        lineage=_lineage(module_id, raw_results.lineage, audit_panel.lineage, retrieval_evidence.lineage),
        reason_code=(
            "NO_TOOL_RESULTS" if not validated
            else "INVALID_OR_FAILED_TOOL_RESULTS_PRESENT" if has_invalid or has_failure
            else None
        ),
    )
