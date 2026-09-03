# API and Literature Basis — P3.S40

## MCP

The official Model Context Protocol tool specification models a tool through a unique name, description and input schema. P3.S40 follows this functional contract while treating MCP as only one optional transport. Internal tools use the same identity and schemas through local function, artifact-query or composite adapters.

## JSON Schema and Pydantic

Requests, results, registries, evidence and handoffs use strict Pydantic models. JSON Schemas are generated from those models against Draft 2020-12, preventing a second manually maintained contract authority.

## Tracing

The trace model follows the OpenTelemetry concept of a trace composed of operation spans and immutable events. S40 stores stable trace/span identifiers and domain attributes without requiring the OpenTelemetry SDK at runtime.

## Lineage

The provenance model is inspired by OpenLineage's run/job/dataset separation and extensible facets. S40 keeps explicit references from P1 raw artifacts and P2 semantic records to tool executions and downstream evidence packages.

## Engineering consequence

No external framework is mandatory. The implementation uses typed ports, immutable registries, explicit adapters and small pure builders. MCP, OpenTelemetry exporters and OpenLineage backends can be added later without changing the domain contracts.
