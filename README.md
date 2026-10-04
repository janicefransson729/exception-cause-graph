# exception_cause_graph

Walks the `__cause__` and `__context__` chains of a Python exception instance and returns a flat list of `(depth, relationship, type, message, traceback)` records — as `ExceptionNode` dataclass instances — suitable for logging, structured error reporting, or rendering.

## Usage

```python
from exception_cause_graph import walk_exception, ExceptionNode, format_walk

try:
    raise ValueError("database connection refused")
except ValueError:
    try:
        raise RuntimeError("retry failed")
    except RuntimeError as exc:
        for node in walk_exception(exc):
            print(node.depth, node.relationship, node.exc_type.__name__, node.message)

# or, for a quick human-readable block:
try:
    raise IOError("disk full") from ValueError(" precondition")
except IOError as exc:
    print(format_walk(exc))
```

`walk_exception(exc)` returns `list[ExceptionNode]`. Each `ExceptionNode` has:

- `depth: int` — 0 for the root, incremented for each link.
- `relationship: str` — `"root"`, `"cause"`, or `"context"`.
- `exc_type: type` — the exception class.
- `message: str` — `str(exc)`.
- `tb: str` — formatted traceback string, or `""` if the exception has no traceback object.

`format_walk(exc)` returns an indented string rendering of the same walk.

## Why

Python's default traceback printer interleaves cause and context chains with prose sentences ("The above exception was the direct cause..."). That is fine for a human reading a terminal but awkward for structured logging or error-reporting pipelines that want one record per exception with an explicit depth and relationship label. This library produces exactly that flat list.

The trade-off: you lose the inline prose that explains *why* one exception led to another. If you need that narrative, use the standard traceback module directly instead.

## Edge cases

- **`__suppress_context__` is ignored.** The library reports what is structurally present on the chain, not what CPython would choose to print. Apply your own suppression policy on top of the returned list if you need print-faithful output.
- **Cycles are guarded.** If `__cause__` or `__context__` links form a cycle (only possible through manual assignment, since normal raising cannot create one), each exception appears at most once and the walk terminates.
- **No traceback → empty `tb` field.** An exception that was constructed but never raised (or whose `__traceback__` was cleared) yields `tb == ""` rather than a synthetic header.
- **`exc_type` is the class object, not a name string.** This lets callers do `isinstance` or subclass checks, at the cost of not being JSON-serialisable as-is.
