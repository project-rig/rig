"""Tests for the contextual-aware function module.
"""
import pytest
from .. import contexts


@pytest.fixture
def object_to_test():
    # Create an object with the mixin to test
    class ObjectWithContext(contexts.ContextMixin):
        def __init__(self):
            contexts.ContextMixin.__init__(self)

        @contexts.ContextMixin.use_contextual_arguments
        def method_a(self, arg0, arg1=contexts.Required, arg2=30):
            return (arg0, arg1, arg2)

    return ObjectWithContext


@pytest.mark.parametrize("arg1", [1, None, 5])
def test_contextmixin_required_passed_no_context(object_to_test, arg1):
    # Create the object
    obj = object_to_test()

    # No context
    assert obj.method_a(1, arg1) == (1, arg1, 30)
    assert obj.method_a(1, arg1, 50) == (1, arg1, 50)
    assert obj.method_a(1, arg1=arg1, arg2=50) == (1, arg1, 50)


@pytest.mark.parametrize("arg1", [1, None, 5])
def test_contextmixin_required_passed(object_to_test, arg1):
    # Create the object
    obj = object_to_test()

    # With context
    with obj.get_new_context(arg1=arg1):
        assert obj.method_a(1) == (1, arg1, 30)
        assert obj.method_a(1, arg2=50) == (1, arg1, 50)


@pytest.mark.parametrize("arg1", [1, None, 5])
def test_contextmixin_required_not_passed_no_context(object_to_test, arg1):
    # Create the object
    obj = object_to_test()

    # No context
    with pytest.raises(TypeError) as excinfo:
        obj.method_a(1)
    assert "arg1" in str(excinfo.value)
    assert "method_a" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        obj.method_a(1, arg2=50)
    assert "arg1" in str(excinfo.value)
    assert "method_a" in str(excinfo.value)


@pytest.mark.parametrize("arg1", [1, None, 5])
def test_contextmixin_required_not_passed(object_to_test, arg1):
    # Create the object
    obj = object_to_test()

    # With context
    with obj.get_new_context():
        with pytest.raises(TypeError) as excinfo:
            obj.method_a(1)
        assert "arg1" in str(excinfo.value)
        assert "method_a" in str(excinfo.value)

        with pytest.raises(TypeError) as excinfo:
            obj.method_a(1, arg2=50)
        assert "arg1" in str(excinfo.value)
        assert "method_a" in str(excinfo.value)

def test_nested(object_to_test):
    # Create the object
    obj = object_to_test()

    # With context
    with obj.get_new_context(arg1=1):
        assert obj.method_a(1) == (1, 1, 30)

        with obj.get_new_context(arg1=2):
            # Check that the stack of contexts is used
            with obj.get_new_context(arg2=3):
                assert obj.method_a(1) == (1, 2, 3)

        assert obj.method_a(1) == (1, 1, 30)
