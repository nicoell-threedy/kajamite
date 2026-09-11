# Unified knowledge engine

Kajamite owns knowledge operations and their reusable consistency rules.
Python, CLI, and MCP consumers use the same engine.
The MCP frontend is optional.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Knowledge engine | Capture, lifecycle transitions, expected revisions, current readback, eligibility, and change receipts. |
| Backend adapter | Public storage operations, indexing, observation search, and graph discovery. |
| Consumer | Source access, authorization, evidence checks, and domain policy. |
| Frontend | Argument transport and result presentation. |

The engine does not certify truth.
A supported claim still needs a current evidence check before ordinary reuse.
Source inaccessibility differs from source change.
A request can exclude a current record because its scope does not match.

## Knowledge representation

Plain notes remain ordinary Markdown with caller-defined kinds and metadata.
A preference can record a user report without independent verification.
A proposal remains a proposal. Arbitrary status metadata cannot establish verified support.

Governed claims carry a versioned record in reserved `kajamite_record` metadata.
The note body presents the current claim.
The record retains evidence, scope, verification, revisions, and event snapshots.
Backend title, type, and permalink metadata remain outside that record.
The engine compares the current body with the record before reuse.
A malformed record or conflicting external edit requires inspection and repair.

Generic note edits cannot replace reserved engine metadata or bypass lifecycle transitions.
Inspection can expose history to an authorized consumer.
Ordinary reuse excludes historical snapshots and unsuitable claims.

## Consistency

An expected revision protects against stale cooperating writers.
A shared backend lock covers comparison, write, and readback.
Basic Memory does not expose an atomic revision-compare operation.
Direct backend tools and human edits remain outside the cooperating lock.

Operation identity supports safe replay of committed transitions.
A repeated identity with different arguments is a conflict.
A transport failure does not prove that a write failed.
After an uncertain result, inspect current state before another write.

A successful receipt identifies the committed revision and readback evidence.
A content-free summary alone never proves persistence.
An index can lag behind committed Markdown.
Search and deletion results must report projection limitations honestly.

## Retrieval

Namespace scope controls retrieval, not authorization.
Consumers supply authorization independently.
Native search results and graph neighbors are candidates.
The engine checks current knowledge before returning governed content.

Observation categories and typed relations come from Basic Memory.
Graph expansion uses physical paths and explicit namespace bounds.
Relation labels alone do not establish evidence dependencies.
Context limits apply after candidate selection, with explicit omissions.

Text search retains bounded native pagination.
Semantic and hybrid modes require explicit backend configuration.
A ranked candidate set cannot prove that no relevant knowledge exists.

## Dependency boundary

The engine depends on the standard library and an injected backend object.
The Basic Memory adapter uses the MCP SDK as a client dependency.
The optional MCP frontend uses that SDK to expose the engine as a server.
An embedded application needs no Kajamite server or ambient session scope.

Source evidence and policy belong to the consumer.
The package contains no provider credentials, model, scheduler, or telemetry exporter.

## Embedded MCP frontend

`kajamite.server.create_server(engine, name="Example", version="1", instructions="...")`
returns an MCP server with the complete knowledge tool catalog, receipt UI, guide,
and text fallback. Add application tools with the returned server's `tool` decorator.
The optional `wrap_operation(name, callable)` hook wraps each knowledge operation.
Use `functools.wraps` to retain its argument schema. A host can add context parameters
with an explicit callable signature when needed by the MCP SDK.
The wrapped callable translates deliberate engine errors to MCP tool errors.
Return receipt fields at the top level when adding host receipt IDs or other metadata.
Preserve error status; an uncertain mutation must not become a success receipt.
Compatible presentation updates come from the installed Kajamite package.
The frontend requires the `mcp` extra; engine-only imports remain dependency-free.

Reuse checks source evidence for actual premises, including transitive premises.
Each premise is checked once per reuse decision. Ordinary note links are not premises.
A failed premise check withholds the dependent with a `dependency_` reason.
Inaccessible evidence does not alter the stored claim or its history; inspection
remains available and must not be presented as freshly verified reuse.
