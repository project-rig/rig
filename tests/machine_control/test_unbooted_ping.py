import pytest

from mock import Mock

from rig.machine_control.unbooted_ping import listen


@pytest.mark.parametrize("should_fail", [False, True])
def test_listen(should_fail, monkeypatch):
    import socket
    mock_socket = Mock()
    monkeypatch.setattr(socket, "socket", Mock(return_value=mock_socket))

    if should_fail:
        mock_socket.recvfrom.side_effect = socket.timeout
    else:
        mock_socket.recvfrom.return_value = ("foo", ("127.0.0.1", 12345))

    # Make sure value returns as expected
    retval = listen(timeout=12.0, port=12345)
    if should_fail:
        assert retval is None
    else:
        assert retval == "127.0.0.1"

    # Make sure parameters were obayed
    assert mock_socket.settimeout.called_once_with(12.0)
    assert mock_socket.bind.called_once_with('0.0.0.0', 12345)
