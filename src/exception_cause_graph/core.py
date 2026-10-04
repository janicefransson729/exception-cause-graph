from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ExceptionNode:
    """A single node in the walked exception chain.

    Fields:
        depth: How far from the root exception this node sits. The root
            is depth 0. A child reachable via the root's ``__cause__``
            or ``__context__`` is depth 1, and so on.
        relationship: "root" for the starting exception, "cause" when
            reached via ``__cause__``, or "context" when reached via
            ``__context__``.
        exc_type: The exception's class object (the ``type`` of the
            instance). Kept as the class rather than a string so callers
            can do ``isinstance`` / subclass checks.
        message: ``str(exc)``. We use ``str(exc)`` rather than
            ``exc.args`` because ``args`` is irregular: some exceptions
            store a single string, some store several, some override
            ``__str__`` to synthesise a message from non-string args.
            ``str(exc)`` is the one uniform, human-readable form.
        tb: The formatted traceback string for this exception, or "" if
            there is no traceback attached. Using the standard
            ``traceback`` module keeps the output identical to what a
            developer sees in an uncaught traceback, which is the one
            format that is already familiar and well-tested.
    """

    depth: int
    relationship: str
    exc_type: type
    message: str
    tb: str


def _format_tb(exc: BaseException) -> str:
    """Return a stringified traceback for ``exc``, or "" if none.

    ``traceback.format_exception`` returns a list of lines; we join them
    into a single string for convenience. When ``exc.__traceback__`` is
    ``None`` (the exception was constructed but never raised, or its
    traceback was cleared), ``format_exception`` still emits the header
    and the exception line. That output is noisy and misleading — it
    implies a traceback where none exists — so in that case we return
    an empty string instead.
    """
    if exc.__traceback__ is None:
        return ""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def walk_exception(exc: BaseException) -> List[ExceptionNode]:
    """Walk the ``__cause__`` and ``__context__`` chains of ``exc``.

    Returns a flat list of :class:`ExceptionNode` tuples ordered
    root-first, then depth-first. At each node the ``__cause__`` chain
    is followed before the ``__context__`` chain, mirroring the order
    Python itself reports them in a default traceback ("The above
    exception was the direct cause..." precedes "During handling of
    the above exception, another exception occurred...").

    Cycles are guarded against: if a node would be visited twice (which
    is only possible through exotic manual manipulation of ``__cause__``
    or ``__context__``, since normal raising cannot create a cycle), the
    walk stops at that branch. This keeps the function total.

    ``__suppress_context__`` is intentionally NOT consulted. The graph
    is about what is structurally present, not about what Python chooses
    to print. A caller rendering a user-facing message can apply their
    own suppression policy on top of this flat list; baking it in here
    would hide information from callers who want the full picture.
    """
    if not isinstance(exc, BaseException):
        raise TypeError(
            "walk_exception expects a BaseException instance, got %r" % type(exc).__name__
        )

    nodes: List[ExceptionNode] = []
    visited: List[int] = []

    def _visit(current: BaseException, depth: int, relationship: str) -> None:
        if id(current) in visited:
            return
        visited.append(id(current))
        nodes.append(
            ExceptionNode(
                depth=depth,
                relationship=relationship,
                exc_type=type(current),
                message=str(current),
                tb=_format_tb(current),
            )
        )
        # cause first, then context — see docstring.
        cause = current.__cause__
        context = current.__context__
        if cause is not None:
            _visit(cause, depth + 1, "cause")
        if context is not None:
            _visit(context, depth + 1, "context")

    _visit(exc, 0, "root")
    return nodes


def format_walk(exc: BaseException) -> str:
    """Return a human-readable, indented rendering of ``walk_exception(exc)``.

    Each node is rendered as::

        [depth:relationship] ExceptionType: message

    followed by its traceback (if any). Children are indented two
    spaces per depth level. This is a convenience for logging and
    debugging; callers needing structured data should use
    :func:`walk_exception` directly.
    """
    lines: List[str] = []
    for node in walk_exception(exc):
        indent = "  " * node.depth
        header = "%s[%d:%s] %s: %s" % (
            indent,
            node.depth,
            node.relationship,
            node.exc_type.__name__,
            node.message,
        )
        lines.append(header)
        if node.tb:
            # Indent the traceback body to align under the header so
            # the whole record reads as one block.
            tb_indented = node.tb.rstrip("\n").replace("\n", "\n" + indent + "  ")
            lines.append(indent + "  " + tb_indented)
    return "\n".join(lines) + "\n"
