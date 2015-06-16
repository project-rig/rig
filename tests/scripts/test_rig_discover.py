"""Test the discover command."""

import pytest

from rig.scripts import rig_discover

from mock import Mock


@pytest.mark.parametrize("should_work", [True, False])
@pytest.mark.parametrize("args,timeout", [("", 6.0), ("-t 100.5", 100.5)])
def test_rig_discover(args, should_work, timeout, monkeypatch, capsys):
    if should_work:
        mock_listen = Mock(return_value="127.0.0.1")
    else:
        mock_listen = Mock(return_value=None)
    monkeypatch.setattr(rig_discover, "listen", mock_listen)

    assert rig_discover.main(args.split()) == int(not should_work)

    out, err = capsys.readouterr()
    if should_work:
        assert out == "127.0.0.1\n"
    else:
        assert out == ""

    assert mock_listen.called_once_with(timeout)
