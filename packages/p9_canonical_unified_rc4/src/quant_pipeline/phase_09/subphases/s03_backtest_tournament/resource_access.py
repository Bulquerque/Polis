"""Read-only access to installed schemas and registries."""

from __future__ import annotations

import json
import re
from importlib.resources import files

_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.json$")


def read_json_resource(category: str, name: str) -> object:
    """Load a packaged JSON resource without permitting path traversal."""

    if category not in {"schemas", "registries"}:
        raise ValueError("category must be schemas or registries")
    if _RESOURCE_NAME.fullmatch(name) is None:
        raise ValueError("invalid JSON resource name")
    resource = files(__package__).joinpath("resources", category, name)
    return json.loads(resource.read_text(encoding="utf-8"))
