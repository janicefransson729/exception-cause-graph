import unittest

from exception_cause_graph import walk_exception, ExceptionNode, format_walk


class TestWalkException(unittest.TestCase):
    def test_single_exception_no_chain(self):
        exc = ValueError("bad value")
        nodes = walk_exception(exc)
        self.assertEqual(len(nodes), 1)
        n = nodes[0]
        self.assertEqual(n.depth, 0)
        self.assertEqual(n.relationship, "root")
        self.assertIs(n.exc_type, ValueError)
        self.assertEqual(n.message, "bad value")
        # never raised -> no traceback object
        self.assertEqual(n.tb, "")

    def test_cause_chain(self):
        try:
            raise KeyError("missing")
        except KeyError as ke:
            try:
                raise ValueError("wrapped") from ke
            except ValueError as ve:
                exc = ve

        nodes = walk_exception(exc)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0].relationship, "root")
        self.assertIs(nodes[0].exc_type, ValueError)
        self.assertEqual(nodes[0].depth, 0)
        self.assertEqual(nodes[1].relationship, "cause")
        self.assertIs(nodes[1].exc_type, KeyError)
        self.assertEqual(nodes[1].depth, 1)
        self.assertEqual(nodes[1].message, "'missing'")

    def test_context_chain(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            try:
                raise TypeError("follow-up")
            except TypeError as te:
                exc = te

        nodes = walk_exception(exc)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0].relationship, "root")
        self.assertIs(nodes[0].exc_type, TypeError)
        self.assertEqual(nodes[1].relationship, "context")
        self.assertIs(nodes[1].exc_type, RuntimeError)
        self.assertEqual(nodes[1].depth, 1)

    def test_cause_preferred_over_context_in_order(self):
        # When both __cause__ and __context__ are set, cause is visited
        # first. We assert ordering only — both children must appear.
        try:
            raise RuntimeError("context source")
        except RuntimeError as ctx:
            try:
                raise KeyError("cause source")
            except KeyError as cause:
                try:
                    raise ValueError("root") from cause
                except ValueError as ve:
                    # __context__ is auto-set to the KeyError here, but
                    # we override it to the RuntimeError to make the
                    # two chains distinct.
                    ve.__context__ = ctx
                    exc = ve

        nodes = walk_exception(exc)
        self.assertEqual(len(nodes), 3)
        self.assertEqual(nodes[0].relationship, "root")
        self.assertEqual(nodes[1].relationship, "cause")
        self.assertEqual(nodes[2].relationship, "context")
        self.assertIs(nodes[1].exc_type, KeyError)
        self.assertIs(nodes[2].exc_type, RuntimeError)

    def test_depth_with_nested_cause_and_context(self):
        # root -> cause -> cause  (three deep)
        #
        # ``raise IndexError from ctx_inner`` explicitly sets
        # IndexError.__cause__ to ctx_inner (the IOError). The fact that
        # IndexError was itself being handled inside an ``except IOError``
        # block also auto-sets IndexError.__context__ to ctx_inner, but
        # since __cause__ and __context__ point at the same object here,
        # the chain is reported as root -> cause -> cause. (The context
        # link is never visited because ctx_inner has already been seen.)
        try:
            raise IOError("level2-context")
        except IOError as ctx_inner:
            try:
                raise IndexError("level2-cause") from ctx_inner
            except IndexError as mid:
                try:
                    raise ValueError("root") from mid
                except ValueError as ve:
                    exc = ve

        nodes = walk_exception(exc)
        self.assertEqual(len(nodes), 3)
        self.assertEqual([n.depth for n in nodes], [0, 1, 2])
        self.assertEqual([n.relationship for n in nodes], ["root", "cause", "cause"])
        self.assertIs(nodes[2].exc_type, IOError)

    def test_traceback_present_when_raised(self):
        try:
            raise ValueError("raised")
        except ValueError as exc:
            nodes = walk_exception(exc)
        self.assertTrue(nodes[0].tb)
        self.assertIn("ValueError", nodes[0].tb)
        self.assertIn("raised", nodes[0].tb)

    def test_exception_with_no_message(self):
        try:
            raise ValueError
        except ValueError as exc:
            nodes = walk_exception(exc)
        self.assertEqual(nodes[0].message, "")

    def test_cycle_guard(self):
        # Manually construct a cycle: a.__context__ = b, b.__context__ = a.
        # walk_exception must terminate and not duplicate nodes.
        a = ValueError("a")
        b = TypeError("b")
        a.__context__ = b
        b.__context__ = a
        nodes = walk_exception(a)
        # a visited, then b visited, then b.__context__ (=a) skipped.
        self.assertEqual(len(nodes), 2)
        self.assertIs(nodes[0].exc_type, ValueError)
        self.assertIs(nodes[1].exc_type, TypeError)

    def test_non_exception_rejected(self):
        with self.assertRaises(TypeError):
            walk_exception("not an exception")  # type: ignore[arg-type]

    def test_node_is_frozen_dataclass(self):
        exc = ValueError("x")
        nodes = walk_exception(exc)
        with self.assertRaises(Exception):
            nodes[0].depth = 99  # frozen dataclass forbids assignment

    def test_exception_type_is_class_not_string(self):
        exc = ValueError("x")
        nodes = walk_exception(exc)
        self.assertTrue(isinstance(nodes[0].exc_type, type))
        self.assertIs(nodes[0].exc_type, ValueError)


class TestFormatWalk(unittest.TestCase):
    def test_basic_format(self):
        try:
            raise ValueError("root error")
        except ValueError as exc:
            text = format_walk(exc)
        self.assertIn("[0:root] ValueError: root error", text)

    def test_format_indents_children(self):
        try:
            raise KeyError("inner")
        except KeyError as ke:
            try:
                raise ValueError("outer") from ke
            except ValueError as ve:
                text = format_walk(ve)

        self.assertIn("[0:root] ValueError: outer", text)
        self.assertIn("  [1:cause] KeyError: 'inner'", text)

    def test_format_ends_with_newline(self):
        try:
            raise ValueError("x")
        except ValueError as exc:
            text = format_walk(exc)
        self.assertTrue(text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
