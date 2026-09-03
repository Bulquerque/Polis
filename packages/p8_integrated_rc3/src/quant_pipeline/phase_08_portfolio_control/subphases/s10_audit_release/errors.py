class AuditReleaseError(Exception):
    """Base typed error for P8.S10."""
class ContractIntegrityError(AuditReleaseError):
    """Closed input contract was violated."""
class TemporalIntegrityError(AuditReleaseError):
    """A timestamp or evaluation commitment violates point-in-time ordering."""
class AuditIntegrityError(AuditReleaseError):
    """Evidence is impossible to audit without fabricating data."""
class ReleaseIntegrityError(AuditReleaseError):
    """Release path or manifest violates sealing rules."""
