# Native retrieval evaluation

`tests/retrieval_benchmark.py` creates an isolated, synthetic Basic Memory
project with semantic retrieval disabled. The fixed corpus contains one long
Markdown source with a unique fact marker near its end, one note linked to that
source, and eight unrelated notes.

The benchmark compares the default entity search with observation retrieval
filtered to the `fact` category. It reports whether each path was recovered,
the total returned snippet characters, backend call count, and elapsed time.
It also verifies that native related retrieval returns the linked source.

Run it against a separately installed Basic Memory executable:

```text
PYTHONPATH=src python tests/retrieval_benchmark.py --basic-memory /path/to/basic-memory
```

The script prints measurements from its current isolated run. They are not a
general performance claim: native indexing, hardware, and backend state affect
elapsed time. The acceptance conditions are that both searches recover the
synthetic source, the focused observation snippet contains the marker and is
shorter than the long document, and the linked target is returned.

## Recorded result

A Linux Python 3.12 run against Basic Memory 0.23.0 passed on 2026-09-10.

| Retrieval | Relevant path recovered | Snippet characters | Backend calls | Elapsed milliseconds |
| --- | --- | --- | --- | --- |
| Default entity search | Yes | 1000 | 1 | 65.378 |
| Current observation with fact filter | Yes | 54 | 2 | 163.785 |

Native graph retrieval also recovered the linked source.
The current-note read adds a backend call and validates the returned candidate.
The observation result reduced context size in this fixture.
These timings are measurements from one run, not latency guarantees.
