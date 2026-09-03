"""Canonical SHA-256 and Ed25519 helpers for integration evidence."""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _decode_base64(value: str, *, expected_length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError(f"{label} must be canonical base64") from exc
    if len(decoded) != expected_length:
        raise ValueError(f"{label} must decode to {expected_length} bytes")
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{label} must use canonical base64 encoding")
    return decoded


def ed25519_public_key_from_base64(value: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(
        _decode_base64(value, expected_length=32, label="Ed25519 public key")
    )


def ed25519_private_key_from_base64(value: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        _decode_base64(value, expected_length=32, label="Ed25519 private key")
    )


def public_key_base64(private_key_base64: str) -> str:
    raw = ed25519_private_key_from_base64(private_key_base64).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def sign_mapping_ed25519(value: Mapping[str, Any], private_key_base64: str) -> str:
    signature = ed25519_private_key_from_base64(private_key_base64).sign(
        canonical_json_bytes(dict(value))
    )
    return base64.b64encode(signature).decode("ascii")


def verify_mapping_ed25519(
    value: Mapping[str, Any],
    signature: str,
    public_key_base64_value: str,
) -> bool:
    try:
        signature_bytes = _decode_base64(
            signature, expected_length=64, label="Ed25519 signature"
        )
        ed25519_public_key_from_base64(public_key_base64_value).verify(
            signature_bytes,
            canonical_json_bytes(dict(value)),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def valid_sha256(value: str) -> bool:
    return (
        len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )
