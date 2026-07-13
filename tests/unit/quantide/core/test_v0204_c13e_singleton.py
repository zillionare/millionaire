"""v0.2-004-coverage-recovery C1.3e: quantide/core/singleton.py.

The ``@singleton`` decorator wraps a class into a callable that returns at
most one instance per original class.  ``_instances`` is keyed by the
*original* (pre-decoration) class object, exposed via ``wrapper.__wrapped__``
(because ``functools.wraps`` copies ``__wrapped__``).  Each test that builds
its own singleton class is self-contained: the freshly-defined class has no
prior cache entry, so no cross-test eviction is required.
"""

from __future__ import annotations

import pytest

from quantide.core.singleton import _instances, singleton


def _evict(cls: object) -> None:
    """Evict ``cls`` from the singleton cache using its original class key."""
    original = getattr(cls, "__wrapped__", cls)
    _instances.pop(original, None)


def test_singleton_returns_same_instance_across_calls() -> None:
    """AC-FR0700-14: repeated calls return the cached singleton instance."""

    @singleton
    class Service:
        def __init__(self) -> None:
            self.value = 0

    _evict(Service)
    a = Service()
    b = Service()
    assert a is b


def test_singleton_honors_first_construction_arguments() -> None:
    """AC-FR0700-15: first-call args populate the instance; later args ignored."""

    @singleton
    class Config:
        def __init__(self, name: str = "default") -> None:
            self.name = name

    _evict(Config)
    first = Config(name="alpha")
    second = Config(name="beta")
    assert first is second
    assert first.name == "alpha"
    assert second.name == "alpha"


def test_singleton_honors_first_positional_arguments() -> None:
    """AC-FR0700-16: first-call positional args persist; later positional ignored."""

    @singleton
    class Counter:
        def __init__(self, start: int) -> None:
            self.value = start

    _evict(Counter)
    a = Counter(10)
    b = Counter(99)
    assert a.value == 10
    assert b.value == 10
    assert a is b


def test_singleton_preserves_name_doc_module_qualname() -> None:
    """AC-FR0700-17: wrapper copies __name__, __doc__, __module__, __qualname__."""

    @singleton
    class Documented:
        """A documented singleton class."""

    _evict(Documented)
    original = Documented.__wrapped__
    assert Documented.__name__ == original.__name__
    assert Documented.__doc__ == original.__doc__
    assert Documented.__module__ == original.__module__
    assert Documented.__qualname__ == original.__qualname__


def test_singleton_first_call_failure_propagates_and_leaves_no_instance() -> None:
    """AC-FR0700-18: a raising __init__ propagates and does not cache a partial instance."""

    @singleton
    class Boom:
        def __init__(self) -> None:
            raise RuntimeError("construction failed")

    _evict(Boom)
    with pytest.raises(RuntimeError, match="construction failed"):
        Boom()
    # No instance cached, so a subsequent call must attempt construction again.
    with pytest.raises(RuntimeError, match="construction failed"):
        Boom()


def test_singleton_works_for_no_arg_class() -> None:
    """AC-FR0700-19: classes without explicit __init__ are supported."""

    @singleton
    class Empty:
        pass

    _evict(Empty)
    a = Empty()
    b = Empty()
    assert a is b
    assert type(a) is Empty.__wrapped__


def test_singleton_two_distinct_classes_get_separate_instances() -> None:
    """AC-FR0700-20: distinct decorated classes maintain independent singletons."""

    @singleton
    class Alpha:
        def __init__(self) -> None:
            self.tag = "alpha"

    @singleton
    class Beta:
        def __init__(self) -> None:
            self.tag = "beta"

    _evict(Alpha)
    _evict(Beta)
    a = Alpha()
    b = Beta()
    assert a is not b
    assert a.tag == "alpha"
    assert b.tag == "beta"
    # Alpha and Beta are distinct wrappers backed by distinct originals.
    assert Alpha.__wrapped__ is not Beta.__wrapped__


def test_singleton_wrapper_exposes_instances_dict() -> None:
    """AC-FR0700-21: wrapper carries an ``_instances`` attribute referencing the cache."""

    @singleton
    class Cached:
        pass

    _evict(Cached)
    assert hasattr(Cached, "_instances")
    assert Cached._instances is _instances
    Cached()
    assert Cached.__wrapped__ in _instances


def test_singleton_instance_shares_class_attribute_access() -> None:
    """AC-FR0700-22: instance retains class-level attributes from the original class."""

    @singleton
    class WithClassAttr:
        style = "primary"

        def __init__(self) -> None:
            self.x = 1

    _evict(WithClassAttr)
    inst = WithClassAttr()
    # The instance's type is the original class, so class attrs are visible.
    assert inst.style == "primary"
    assert inst.x == 1


def test_singleton_after_eviction_recreates_instance_with_new_args() -> None:
    """AC-FR0700-23: evicting the cache key allows a fresh construction with new args."""

    @singleton
    class Reloadable:
        def __init__(self, label: str = "v1") -> None:
            self.label = label

    _evict(Reloadable)
    first = Reloadable(label="v1")
    assert first.label == "v1"
    # Evict and rebuild with different args.
    _evict(Reloadable)
    second = Reloadable(label="v2")
    assert second.label == "v2"
    assert first is not second
