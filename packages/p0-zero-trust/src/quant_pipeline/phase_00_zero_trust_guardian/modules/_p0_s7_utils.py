from __future__ import annotations

from . import _p0_s7_common as _common

REPOSITORY_ROOT = _common.REPOSITORY_ROOT
FORBIDDEN_FIELDS = _common.FORBIDDEN_FIELDS

created_at = _common.created_at
digest = _common.digest
reject_forbidden = _common.reject_forbidden
list_field = _common.list_field
unique = _common.ensure_unique
validate_upstream = _common.validate_upstream
envelope = _common.envelope


def internal_file(value, label):
    _common.REPOSITORY_ROOT = REPOSITORY_ROOT
    return _common.resolve_repository_path(value, label)


def mapping(value, label):
    _common.REPOSITORY_ROOT = REPOSITORY_ROOT
    return _common.load_mapping(value, label)
