"""Test the test order markers implemented in conftest."""

import pytest


class TestOrderSimple(object):

    called = []

    def test_d(self):
        # This test doesn't care when it is run!
        pass

    @pytest.mark.order_after("b", "a")
    @pytest.mark.order_id("c", "magic")
    def test_c(self):
        TestOrderSimple.called.append("c")
        assert TestOrderSimple.called == "a b c".split()

    @pytest.mark.order_id("b", "magic")
    def test_b(self):
        TestOrderSimple.called.append("b")
        assert TestOrderSimple.called == "a b".split()

    @pytest.mark.order_before("b")
    @pytest.mark.order_id("a", "magic")
    def test_a(self):
        TestOrderSimple.called.append("a")
        assert TestOrderSimple.called == "a".split()
