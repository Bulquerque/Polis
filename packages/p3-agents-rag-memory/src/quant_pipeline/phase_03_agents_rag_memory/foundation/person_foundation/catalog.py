"""Generated documentation and schema helpers for the canonical tag registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..learning_feedback.canonical import content_hash, ensure_mapping


def tag_registry_catalog(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic machine-readable catalog from the runtime registry."""

    value = ensure_mapping(registry, "personality_tag_registry")
    categories = []
    aliases: dict[str, str] = {}
    for category in value.get("categories", ()):  # validated by S4.M01
        normalized_tags = []
        for tag in category["tags"]:
            normalized_tags.append(
                {
                    "tag_id": tag["tag_id"],
                    "description": tag["description"],
                    "status": tag.get("status", "ACTIVE"),
                    "aliases": tuple(sorted(tag.get("aliases", ()))),
                }
            )
            aliases.update({alias: tag["tag_id"] for alias in tag.get("aliases", ())})
        categories.append(
            {
                "category_id": category["category_id"],
                "tags": tuple(sorted(normalized_tags, key=lambda item: item["tag_id"])),
            }
        )
    result = {
        "catalog_id": "P3_PERSONALITY_TAG_CATALOG",
        "catalog_version": value["registry_version"],
        "source_registry_id": value["registry_id"],
        "source_registry_hash": value["registry_hash"],
        "categories": tuple(sorted(categories, key=lambda item: item["category_id"])),
        "alias_to_tag": dict(sorted(aliases.items())),
    }
    return {**result, "catalog_hash": content_hash(result)}


def render_tag_registry_markdown(registry: Mapping[str, Any]) -> str:
    """Render stable human documentation from the same registry used by code."""

    catalog = tag_registry_catalog(registry)
    lines = [
        "# Canonical personality tags",
        "",
        f"Registry: `{catalog['source_registry_id']}`",
        f"Version: `{catalog['catalog_version']}`",
        f"Hash: `{catalog['source_registry_hash']}`",
        "",
    ]
    for category in catalog["categories"]:
        lines.extend((f"## {category['category_id']}", ""))
        for tag in category["tags"]:
            aliases = ", ".join(f"`{item}`" for item in tag["aliases"]) or "—"
            lines.append(
                f"- `{tag['tag_id']}` — {tag['description']} "
                f"(status: {tag['status']}; aliases: {aliases})"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
