# Editorial composition and maintenance

Kajamite helps an agent make and maintain ordinary Markdown notes. It provides
bounded retrieval and reliable mutations; the calling agent supplies the
reader, purpose, source interpretation, and editorial judgment. A valid
receipt, a correct fact, or a successful backend write does not certify that a
document is useful.

This design applies to ordinary notes. Governed records retain their lifecycle
and metadata rules and do not enter generic revision or collection
consolidation.

## Evidence and adaptation

| Observed mechanism | Reported tradeoff or failure | Adopted direction | Deliberate adaptation | Package surface |
| --- | --- | --- | --- | --- |
| ReMe's extraction instructions select fewer, richer units and split only for independent future use or evolution. | File-by-file summaries and passing recaps produce repetitive, weakly reusable memory. | Choose placement before writing: no write, integrate, create, split, or consolidate. | This is guidance, not a required taxonomy or one-fact-per-file rule. | Reusable skill; authoring guidance. |
| ReMe's purpose-specific integration prompts preserve reasons, exceptions, and explanatory links. | Its additive-link preference can make pruning difficult; small preference units can fragment a topic. | Write for a reader's purpose and explain relationships in links. Preserve meaningful exceptions and examples. | Links and details may be removed or moved when they no longer help the current explanation. No fixed word limit applies. | Reusable skill; editorial examples. |
| Hindsight's delta operation identifies blocks and copies untouched blocks through unchanged. | Historical reports included flattened Markdown tables and loss of earlier material during refresh. | Protect unaffected bytes while allowing connected passages to change together. | Exact passages, rather than a Markdown parser or model-generated blocks, are the stable boundary. A deliberate full reorganization is allowed when it improves the document. | `knowledge_revise`; read hashes; receipts. |
| Hindsight's page prompts integrate into existing sections and keep concrete examples. | A historically reported page could contain individually accurate statements about the wrong subject. | Revise the current whole explanation, reconcile overlaps, and retain useful examples. | The engine verifies operations only; it does not judge subject, truth, or prose. | Reusable skill; `knowledge_revise`. |
| OpenViking's typed templates retain answerable facts, reasons, and exceptions. | Type-specific accumulation and reported duplicate procedures show that good new-write rules do not clean an accumulated collection. | Inspect a bounded selected collection and let the caller choose a canonical explanation and reconcile references. | Exact equality is a candidate, never a deletion decision. Shortness, age, headings, sparse links, and semantic similarity are not automatic quality scores. | `knowledge_inspect_collection`; existing read/context/related operations. |

The sources are the ReMe revision `9ad3dafce5666c55e8cd5b16cc5ffba42da6cce1`,
Hindsight revision `bde55237f53bf55aacd048b01e29d7dc23b83a85`, and
OpenViking revision `e757dd3749275718406c66fd87766c44556626e0`. The
historical Hindsight table and scope reports informed failure mechanisms; they
do not assert that those fixes remain absent. The full research record and its
evidence limits are private to the consumer project.

## Editorial principles

1. Start with the intended reader and use. Place new material only after
   inspecting relevant notes.
2. Treat a note as a coherent unit of meaning. Split when independent use or
   evolution warrants it, not merely to make facts atomic or files short.
3. Combine sources into a present explanation. Distinguish evidence, inference,
   preference, proposal, and decision where that distinction matters.
4. Revise the existing account when new material changes it. Do not preserve a
   conversation recap merely because it is older.
5. Preserve useful examples, exceptions, and unaffected structure. Prune
   redundancy and move supporting detail when it improves comprehension.
6. Use links to explain a relationship and keep shared material in one useful
   home. An overview is optional and must add orientation rather than duplicate
   its notes.
7. State what remains unknown. Factual support, editorial usefulness, and a
   successfully verified operation are separate claims.

## Revision interface

`knowledge_edit` remains compatible for one exact replacement and/or a metadata
merge. This ordinary-note operation supports connected revision:

```
knowledge_revise(
    identifier: str,
    expected_content_sha256: str,
    replacements: list[{"find_text": str, "replacement": str}],
    preview: bool = false,
)
```

`expected_content_sha256` is the lowercase SHA-256 digest of the complete
current UTF-8 note body. It uses the same body representation as
`knowledge_change.before.content_sha256` and
`knowledge_change.after.content_sha256`; it is not a digest of a paged preview,
rendered Markdown, identifier, or metadata. `knowledge_read` and each ordinary
note returned by `knowledge_context` expose `content_sha256`, even when their
`content` field is truncated. Metadata is deliberately outside this precondition:
the revision operation neither accepts nor writes metadata. A generic revision
of a governed record is rejected before mutation.
To update selected passages in a governed claim, use
`knowledge_record_transition` with `action="revise"`, the current expected
record revision, a unique operation ID, and `changes.replacements` in the same
shape. This transition has no preview mode. It preserves unselected claim text
and record history; without fresh verification the result needs revalidation.

`replacements` contains one to 100 ordered entries. Each nonempty `find_text`
must occur exactly once in the same original complete body. Selected ranges must be disjoint; repeated or
overlapping selections, a missing selection, an invalid digest, or a stale body
reject the entire request before any write. The engine computes the result from
the original body, applies the replacements in source order, and preserves every
unselected byte. It does not parse and re-render Markdown.

With `preview=true`, the operation performs the same validation and returns
`preview=true`, the exact `proposed_content`, and
`proposed_content_sha256`; it makes no write and returns no change receipt. On
an unchanged source, applying the same request with `preview=false` produces
that exact body. A preview is computation, not approval: application always
rechecks the expected digest while holding the cooperating-writer lock.

With `preview=false`, the operation uses the existing public backend mutation
and full readback. Its success result follows the current mutation shape:
`note`, `mutation`, `knowledge_change`, and `knowledge_change_text`. The
receipt operation is `revise`, identifies the before and after complete-body
hashes, lists the ordered exact replacements as bounded values, and says only
that the write was read back successfully. An uncertain result has no success
receipt and must be inspected before retrying.

This is one-note consistency. It is not a transaction across notes and cannot
protect against a direct backend writer or human editor outside the shared lock.

## Collection inspection and consolidation

Current `knowledge_list`, `knowledge_context`, and `knowledge_related` remain
the general browse, bounded-read, and graph-retrieval operations. They cannot
by themselves return a recursively bounded collection inventory with complete
body revisions: listing has no content hash, and context intentionally limits
body text. This read-only operation fills that gap:

```
knowledge_inspect_collection(
    namespace: str,
    recursive: bool = true,
    cursor: str | None = null,
    page_size: int = 20,
)
```

The namespace is explicit. The opaque cursor is bound to namespace, recursion,
and page size; another scope rejects it. Each response returns `notes` with the
canonical identifier, path, permalink when available, title, and complete-body
`content_sha256`, plus `next_cursor`, `has_more`, `exhausted`, `scanned_notes`,
and explicit read/list omissions or errors. It is a live bounded scan, not a
snapshot. Changed native totals require recovery after traversal ends.
The cursor then restarts at the first page.
Deduplicate repeated identities. Exhaustion with `partial=true` or
`index_changed=true` does not establish completeness. Preserve returned hashes
and reread selected notes before writing.

The initial mechanically reliable candidate is an `exact_duplicate` group:
two or more successfully read notes in the returned page with equal complete
body digests. Its scope is the returned page, so absence is never a claim that
the collection has no duplicates. Shared references and unresolved internal
links are not emitted until public backend results support them without a
lossy Markdown-link parser. Semantic overlap, sparse links, age, length, and
heading counts remain caller judgment, not inspection findings.

Focused restructuring selects complete notes and applies explicit revisions.
Broader maintenance repeats bounded inspection and retains its omissions and
continuation. For consolidation, the caller inspects complete selected notes,
identifies the surviving explanation and independently useful material, authors explicit
ordinary-note revisions, and uses `knowledge_revise` for each note. The caller
orders the changes and carries each source's expected content hash. After a
partial failure it rereads all affected notes, reports per-note outcomes, and
resumes only outstanding edits whose expected bodies still match. Kajamite does
not silently delete a source, create redirects, repair unscanned backlinks, or
claim rollback across Basic Memory writes.

## Evidence limits

The package tests deterministic operation properties: selection validation,
unchanged byte preservation, stale-source rejection, readback, bounded scans,
and honest partial results. Those tests do not measure prose quality or prove
that a consolidation is semantically correct. Documentation examples illustrate
the directions above; they are not a benchmark or universal score.

## Integrated review

The implemented workflow addresses the evidence table without copying an
upstream prompt or claiming their reported failures are universal. Deliberate
placement and flexible note shapes address richer units and purpose-specific
writing. `knowledge_revise` protects exact untouched spans and supports an
intentional current-account rewrite, but cannot judge whether the revised account
has the right subject. `knowledge_inspect_collection` separates bounded corpus
maintenance from write-time placement and reports exact duplicate candidates only.

Source-informed design, deterministic regression tests, isolated native
commissioning, and human editorial review are distinct evidence. The current
working tree has deterministic source and installed-package test evidence. Its
isolated Basic Memory commissioning covers grouped revision and bounded collection
inspection as operation mechanics. Neither form of automation measures prose
quality, semantic consolidation, or reader usefulness.
