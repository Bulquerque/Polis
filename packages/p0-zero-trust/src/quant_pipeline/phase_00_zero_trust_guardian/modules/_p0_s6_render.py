from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
import hashlib
import json

from ._p0_s6_core import ContractValidationError

CSS = """
:root {
  font-family: Inter, system-ui, Arial, sans-serif;
  color: #111;
  background: #f5f6f8;
}
body { margin: 0; }
header { background: #111827; color: #fff; padding: 22px 28px; }
main { padding: 24px; max-width: 1500px; margin: auto; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}
.card {
  background: #fff;
  border: 1px solid #dfe3ea;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 2px #0000000d;
}
.phase { margin-top: 12px; }
.badge { padding: 3px 8px; border-radius: 999px; background: #eef2ff; font-size: 12px; }
.critical { background: #fee2e2; }
.warning { background: #fef3c7; }
.healthy { background: #dcfce7; }
.muted { color: #6b7280; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 9px; border-bottom: 1px solid #e5e7eb; }
button { border: 0; background: none; font: inherit; cursor: pointer; padding: 0; }
.details { display: none; padding-top: 8px; }
.phase.open .details { display: block; }
""".strip()

JS = """
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-phase]');
  if (!button) return;
  const row = button.closest('.phase');
  if (row) row.classList.toggle('open');
});
""".strip()


def render_dashboard(tower: dict[str, Any], panel: dict[str, Any]) -> dict[str, str]:
    payload = {"control_tower": tower, "phase_health_panel": panel}
    data_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2)
    return {
        "index.html": _render_html(tower, panel),
        "assets/dashboard.css": CSS,
        "assets/dashboard.js": JS,
        "data/control_tower.json": data_json,
    }


def write_files(files: dict[str, str], output_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for relative, content in sorted(files.items()):
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ContractValidationError(f"unsafe dashboard output path: {relative}") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        path.write_bytes(data)
        entries.append(_file_entry(relative, data))
    return entries


def file_entries(files: dict[str, str]) -> list[dict[str, Any]]:
    return [_file_entry(path, content) for path, content in sorted(files.items())]


def _file_entry(path: str, content: str | bytes) -> dict[str, Any]:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _render_html(tower: dict[str, Any], panel: dict[str, Any]) -> str:
    summary = tower.get("development_summary", {})
    alerts = tower.get("alert_summary", {})
    phases = panel.get("phase_statuses", [])
    cards = _cards(summary, alerts, tower)
    rows = "".join(_phase_row(phase) for phase in phases)
    generated = escape(str(tower.get("created_at", "unknown")))
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>P0 Control Tower</title>
  <link rel="stylesheet" href="assets/dashboard.css">
</head>
<body>
<header>
  <h1>P0 — Global Control Tower</h1>
  <div>Snapshot: {generated}</div>
</header>
<main>
  <section class="grid">{cards}</section>
  <section class="card" style="margin-top:18px">
    <h2>Fases</h2>
    <table>
      <thead><tr><th>Fase</th><th>Desenvolvimento</th><th>Testes</th><th>Saúde</th><th>Qualificação</th><th>Prontidão</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
</main>
<script src="assets/dashboard.js"></script>
</body>
</html>"""


def _cards(summary: dict[str, Any], alerts: dict[str, Any], tower: dict[str, Any]) -> str:
    values = (
        ("Fases", summary.get("phases_total", 0)),
        ("Implementadas", summary.get("phases_implemented", 0)),
        ("Qualificadas", summary.get("phases_qualified", 0)),
        ("Alertas críticos", alerts.get("critical", 0)),
        ("Warnings", alerts.get("warning", 0)),
        ("Release", tower.get("release_readiness", "UNKNOWN")),
    )
    return "".join(_card(title, value) for title, value in values)


def _card(title: str, value: Any) -> str:
    return (
        "<div class='card'>"
        f"<div class='muted'>{escape(str(title))}</div>"
        f"<h2>{escape(str(value))}</h2>"
        "</div>"
    )


def _phase_row(phase: dict[str, Any]) -> str:
    pid = escape(str(phase.get("phase_id", "?")))
    name = escape(str(phase.get("phase_name", pid)))
    reasons = ", ".join(str(x) for x in phase.get("readiness_reasons", [])) or "Sem bloqueios"
    details = escape(reasons)
    return (
        "<tr class='phase'>"
        f"<td><button data-phase='1'><strong>{pid}</strong> — {name}</button>"
        f"<div class='details muted'>{details}</div></td>"
        f"<td>{_badge(phase.get('development_status'))}</td>"
        f"<td>{_badge(phase.get('test_status'))}</td>"
        f"<td>{_badge(phase.get('health_status'))}</td>"
        f"<td>{_badge(phase.get('qualification_status'))}</td>"
        f"<td>{_badge(phase.get('readiness'))}</td>"
        "</tr>"
    )


def _badge(value: Any) -> str:
    text = escape(str(value or "UNKNOWN"))
    lowered = text.lower()
    if any(token in lowered for token in ("fail", "critical", "not_ready")):
        css = "critical"
    elif any(token in lowered for token in ("warn", "partial", "running", "eligible")):
        css = "warning"
    elif any(token in lowered for token in ("healthy", "pass", "ready", "qualified", "implemented")):
        css = "healthy"
    else:
        css = ""
    return f"<span class='badge {css}'>{text}</span>"
