# Change result presentation

The card helps a reader answer three questions: what happened, which notes were
involved, and what changed. It reports stored knowledge changes, not external
business events. A saved status field does not prove a reservation or approval.

## Information priority

The note title and the actual supplied change form the primary content. Save
outcomes remain visible and do not certify external business facts. Expanded
view shows exact file paths. Partial results, failed items, uncertain writes and
replayed outcomes preserve their distinct meaning.

Inline and expanded detail use one comparison renderer with exact wrapped
source strings, before/after gutters and word-level changes. Deletions retain
strikethrough; additions use a highlight without underlining. Long lines wrap.
Large unchanged or edited regions have a single disclosure seam. Expansion
retains its DOM control and focus, reveals text where the seam was, and moves
the fold affordance into the gutter. Ancestor scroll compensation preserves the
activated reading location. No global collapse toolbar, inline word truncation
controls, numeric edit navigator or comparison legend is added.

Inline comparison has a bounded vertical scroll area; title and save footer stay
outside it. Expanded detail owns its page scroll and offers unified/split layouts
when space permits. The same comparison surfaces stay mounted while opening
or closing detail; a new result resets disclosure state. Long source values and
identifiers wrap without horizontal overflow.

Meaningful metadata fields remain visible under their supplied labels.
Bookkeeping counters do not inflate changed-content counts. Governed receipts
project validated semantic fields without frontend decoding of stored journals;
legacy metadata remains inspectable. Batch items retain note identity and errors.
Optional technical details retain verification, coverage and the raw result.

Receipt snippets are not complete notes. Truncated source remains explicit and
cannot be recovered by disclosure. A complete created claim is displayed only
when receipt-bound hash and revision validation succeeds. Compact mutation
summaries restore exact audit data only after digest and identity checks. Late
asynchronous results cannot replace a newer request or cancellation. Source text
is rendered as inert React content; no additional retrieval is performed.

## Appearance and embedding

The default palette derives from the public Shopify theme export at
https://tweakcn.com/r/themes/cmr2oqrzb000104ky3d4o23e0. Primary and accent tokens
shift toward yellow-green, with light primary `oklch(0.78 0.18 119)` and dark primary
`oklch(0.84 0.18 119)`. Neutral surfaces, radius, and typography structure remain.
System font stacks avoid font downloads. Exported theme styles are represented as
static tokens, not a runtime dependency on the theme service.

Both the document root and body are transparent. The card uses its opaque card
token. The host controls the surface behind the iframe; it may still apply its own
wrapper background. Default tokens, host appearance, and explicit adopter tokens
retain their existing precedence. The default palette uses the same semantic
colors as configured themes, including comparison highlights.

## Basis and acceptance limits

The hierarchy applies progressive disclosure to secondary information while
keeping primary facts and errors visible. See
https://www.nngroup.com/articles/progressive-disclosure/ and the official shadcn
composition guidance at https://ui.shadcn.com/docs/components/radix/collapsible.
The retained Card, Button, and Collapsible primitives provide semantic controls,
focus behavior, and controlled disclosure. No new component library is required.

Browser acceptance covers visible summaries, field labels, hidden diagnostics,
light/dark and adopter tokens, transparent embedding, narrow widths, inert text,
pagination, and host expansion fallback. Synthetic previews test the actual bundle.
They do not establish user usability success or actual ChatGPT host presentation;
those require review in the target host.

## Interface study

The standalone [MCP UI study](demos/mcp-ui.html) is a synthetic prototype for
understanding what changed in a note and whether anything needs attention.
Cards lead with concrete content and one save-outcome sentence. The full-height
detail surface identifies the file and provides more reading space. It uses the
same comparison grammar as the card.

### Process and responsibility

Scan the result → read the visible edit → reveal omitted evidence → continue
reading → optionally refold or open detail. A preview ends before saving. An
uncertain result requires inspection before another write. Multiple notes retain
their independent outcomes.

The source owns exact text, identifiers and save evidence. The agent supplies
faithful editorial wording. The renderer owns disclosure and the reading
position; it does not infer external facts or certify them from a saved status.
The host owns placement. No prototype interaction saves, retries or undoes a
knowledge operation.

### Semantic structure

| Concern | Pattern | Stable surface and depth |
| --- | --- | --- |
| Subject | Note title; full-view file path | Visible identity, with wrapping for long paths |
| Substance | Shared line comparison and word highlights | Exact supplied content; the same typography and gutter in card and detail |
| Outcome | Icon and one sentence | Saved, proposed, unchanged or uncertain, attached to the content |
| Omitted evidence | One full-width disclosure seam | Hidden count and content kind form one control |
| Revealed evidence | Text with a quiet gutter fold affordance | No missing-content placeholder occupies a revealed row |
| Reading | Peer reading mode when text exists | Complete bodies stay distinct from bounded passages |
| Technical source | Secondary disclosure under prototype controls | Source data remains available without occupying the routine comparison |

### Local reveal workflow

The specialized workflow is limited to a hidden region, adjacent text and the
reader's location. It does not reorganize the broader knowledge model. This
scope warrants two-way tracing because exact hunk ranges cannot express where
a reader is currently looking, and disclosure repeatedly interrupts that task.

| Shared node | Source-side evidence | Reader question and action | View contract |
| --- | --- | --- | --- |
| Hidden region | Changed or unchanged line ranges and stable identities | Is anything omitted here? Reveal it locally | One seam describes precisely the missing content |
| Reading anchor | Adjacent line identity, control identity and scroll ancestors | Continue from the place clicked | Keep the same focused control and preserve its screen position |
| Revealed region | Exact supplied rows | Inspect and optionally refold | Text occupies the region; folding lives in its gutter |
| Unavailable evidence | Explicit truncated or absent source values | Can the full edit be inspected? | Missing source data never becomes an expandable fabricated result |

The source-aligned fallback is the full exact comparison with a filename and
shared gutter. A renderer cannot recover unavailable text. Declaration of a
prose passage permits soft-wrap normalization for comparison only; the source
and reading view retain exact text. Code and arbitrary Markdown are not
normalized.

### Value and layout grammar

Title and path identify the subject. Before/after text and changed words compose
one comparison. Count, content kind and disclosure state compose one omission
control. Save icon and sentence compose one outcome. Unrelated revision counters
do not enter these values.

The four-pixel rhythm and shared type roles apply to both surfaces. Labels use
secondary contrast; body text carries the strongest neutral contrast. Small
removed and added accents repeat in the gutter and word highlights. Deleted
words use strikethrough; added words have no underline. Signs,
positions and accessible labels preserve meaning without color. A redundant
comparison legend is unnecessary.

The card may bound a large comparison with a local vertical scrollbar while
keeping its title and save footer visible. Detail uses its page scroll. Exact
text wraps without arbitrary inline truncation widgets. Fold controls do not
insert global toolbars or extra blank rows when content is expanded.

### Interaction invariants

- The entire collapsed seam is one accessible button.
- Expansion retains that button and its focus identity.
- A revealed region uses a small gutter affordance, not a full-width hide row.
- Expansion and collapse preserve the clicked control's vertical screen position
  through scroll compensation, within scroll-boundary constraints.
- Disclosure state survives switching comparison modes and reopening detail.
- Card and detail use one rendering primitive and one fold-state model.
- Unknown completion remains unknown; incomplete excerpts remain incomplete.

### Evidence and scope

The 55 scenes cover mutation-result states, varied change sizes and comparison
edge cases. Prototype controls expose appearance and source-case coverage;
these are not product workflow categories. Supplied summaries are fixture
content, not a demonstrated automatic semantic-summary capability.

The design references structural separators in [Pierre Diffs](https://diffs.com/docs),
aligned comparisons in [Zed](https://zed.dev/blog/split-diffs), and disclosure in
[VS Code](https://code.visualstudio.com/updates/v1_82). No referenced library is
installed. Native host placement, receipt-bound hydration and asynchronous
result ordering remain production implementation concerns.

Validation must measure actual pointer and keyboard interactions: before/after
screen position, focused DOM identity, first revealed text, scroll movement,
refolding, and consistent appearance in both surfaces. Fixture breadth alone
does not establish spatial continuity or native host acceptance.

Validation: actual pointer expansion, pointer collapse and Enter-key expansion
retain the same focused DOM button with zero measured vertical drift in the
representative desktop and narrow cases. The first revealed row occupies the
prior seam location. Shared label and row styles, source reconstruction, 550
appearance combinations and all 55 fallback placements pass browser checks.
Prose split view gives each text cell the available column width; its normalized
comparison has no physical line-number track. A 720 CSS-pixel viewport at twice
device scale checks enlarged-layout reflow; native host zoom remains unverified.

## Production acceptance

The packaged renderer is validated separately from the synthetic study. Browser
assertions run through Chrome DevTools Protocol with real browser time and the
pinned Node development runtime. They cover digest/identity mismatches, delayed
result ordering, host display refusal and timeout, exact claim snapshots,
themes, transparent embedding, inert text, semantic fields, partial outcomes,
long lines and narrow layouts. Sequence tests cover exact reconstruction across
Unicode, whitespace, multiline changes and the bounded large-input fallback.
Native client-host acceptance remains separate from synthetic host checks.
