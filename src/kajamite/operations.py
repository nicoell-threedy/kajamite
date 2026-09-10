"""Transport-independent operation vocabulary."""

OPERATIONS = {
    "knowledge_list": ("list", "Browse notes and child namespaces (ordinary directories). Depth 1 lists immediate children; use pages for large listings."),
    "knowledge_search": ("search", "Full-text search within explicit namespaces. recursive=true includes descendants; root '/' selects the base. Follow next_cursor even when results are empty: scans are bounded and has_more means search is incomplete. No semantic-search claim."),
    "knowledge_read": ("read", "Read one exact note identifier returned by search or create. Content is paged by character offset; follow next_offset before editing truncated notes."),
    "knowledge_create": ("create", "Write supplied Markdown and optional metadata into an explicit namespace. Creates parent directories as needed and never silently overwrites. Returns the backend-assigned identifier and a verified change receipt; no template or relationship is inserted."),
    "knowledge_edit": ("edit", "Change exactly one current body passage and/or merge metadata on an existing note. Pass both find_text and replacement for a body edit. Returns a verified change receipt. Read back after an uncertain result before retrying."),
    "knowledge_context": ("context", "Read multiple selected notes under one total body-character budget, using either a namespace page or exact identifiers. Returns structured notes, omissions and continuation. Links are not followed implicitly."),
    "knowledge_move": ("move", "Move an exact note or namespace through Basic Memory. Set is_namespace=true for a directory move. Destination is a relative path; inspect the returned receipt and addresses, and reconcile uncertain results before retrying."),
    "knowledge_related": ("related", "Gather bounded native graph neighbors in explicit namespaces, then read current eligible knowledge."),
    "knowledge_record_maintain": ("record_maintain", "Mark affected dependent records for review in a bounded namespace inventory. Reports partial progress and safe replay."),
    "knowledge_record_remove": ("record_remove", "Remove one exact governed record at an expected revision. Reports backend deletion and bounded index-removal evidence; does not erase backups."),
    "knowledge_record_create": ("record_create", "Create one governed claim with evidence, scope, and revision history. Returns committed revision and receipt."),
    "knowledge_record_transition": ("record_transition", "Apply an explicit lifecycle transition with expected revision and unique operation identity. Inspect uncertain results before retrying."),
}
