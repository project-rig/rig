import pytest

from mock import Mock

from six import next

from rig import wizard


def test_success_str():
    # Make sure the success exception prints like its data
    with pytest.raises(wizard.Success) as excinfo:
        raise wizard.Success({"this is a": "dictionary"})

    assert str(excinfo.value) == "{'this is a': 'dictionary'}"


@pytest.mark.parametrize("option,dimensions", [(0, (2, 2)), (1, (8, 8))])
def test_dimensions_wizard_standard_types(option, dimensions):
    # Make sure we can select standard machine types
    with pytest.raises(wizard.Success) as excinfo:
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(option)

    assert excinfo.value.data["dimensions"] == dimensions


@pytest.mark.parametrize("num_boards,dimensions", [(3, (12, 12)),
                                                   (24, (48, 24))])
def test_dimensions_wizard_num_boards(num_boards, dimensions):
    # Make sure we can select systems by number of boards
    with pytest.raises(wizard.Success) as excinfo:
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(2)  # Multiple SpiNN-5s
        g.send(num_boards)

    assert excinfo.value.data["dimensions"] == dimensions


@pytest.mark.parametrize("dimensions", [(12, 12), (48, 24)])
def test_dimensions_wizard_custom(dimensions):
    # Make sure we can select systems by size
    with pytest.raises(wizard.Success) as excinfo:
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(3)  # Custom
        g.send("{}x{}".format(*dimensions))

    assert excinfo.value.data["dimensions"] == dimensions


def test_dimensions_wizard_invalid():
    # Shouldn't be able to enter non multiples of three boards nor
    # non-numerical system sizes.
    with pytest.raises(wizard.Failure):
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(2)  # Num boards
        g.send("4")
    with pytest.raises(wizard.Failure):
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(2)  # Num boards
        g.send("foo")
    with pytest.raises(wizard.Failure):
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(3)  # Custom
        g.send("foo")
    with pytest.raises(wizard.Failure):
        g = wizard.dimensions_wizard()
        g.send(None)
        g.send(3)  # Custom
        g.send("fooXbar")


@pytest.mark.parametrize("should_work", [True, False])
def test_ip_address_wizard_auto(should_work, monkeypatch):
    if should_work:
        mock_listen = Mock(return_value="127.0.0.1")
    else:
        mock_listen = Mock(return_value=None)

    monkeypatch.setattr(wizard, "listen", mock_listen)

    # Make sure automatic discovery can be used
    with pytest.raises((wizard.Success, wizard.Failure)) as excinfo:
        g = wizard.ip_address_wizard()
        g.send(None)
        g.send(0)  # Automatic
        g.send(None)  # Press enter
        g.send(None)  # Dismiss info

    if should_work:
        assert isinstance(excinfo.value, wizard.Success)
        assert excinfo.value.data["ip_address"] == "127.0.0.1"
    else:
        assert isinstance(excinfo.value, wizard.Failure)


def test_ip_address_wizard_manual():
    # Make sure hostname are accepted
    with pytest.raises(wizard.Success) as excinfo:
        g = wizard.ip_address_wizard()
        g.send(None)
        g.send(1)  # Manual
        g.send("hostname")
    assert excinfo.value.data["ip_address"] == "hostname"

    # Make sure blanks are rejected
    with pytest.raises(wizard.Failure):
        g = wizard.ip_address_wizard()
        g.send(None)
        g.send(1)  # Manual
        g.send("")


@pytest.mark.parametrize("commands,expected", [
    # Runs through all types of message
    ([3,  # Custom size
      "24x12",  # The size
      0,  # Automatic
      None,  # "Press enter"
      None],  # Info...
     {"dimensions": (24, 12), "ip_address": "127.0.0.1"}),
    ([3,  # Custom size
      "24x12",  # The size
      "",  # (Default to automatic)
      None,  # "Press enter"
      None],  # Info...
     {"dimensions": (24, 12), "ip_address": "127.0.0.1"}),
    # Make the wizard fail
    ([2,  # Number of boards
      "4"],  # (not a multiple of three)
     None),
    # Give an invalid multiple choice answer
    ([""], None),
    (["foo"], None),
    (["4"], None),
    (["-12"], None),
])
def test_cat_and_cli_wrapper(commands, expected, monkeypatch):
    """Run through the wizard's command line interface and make sure it
    succeeds and fails as expected."""
    # Make the listener always succeed
    mock_listen = Mock(return_value="127.0.0.1")
    monkeypatch.setattr(wizard, "listen", mock_listen)

    # Stream in the specified commands
    commands_iter = iter(commands)

    def fake_input(message=None):
        return next(commands_iter)
    monkeypatch.setattr(wizard, "input", fake_input)

    # The response should be as expected
    assert wizard.cli_wrapper(wizard.cat(wizard.dimensions_wizard(),
                                         wizard.ip_address_wizard())) \
        == expected
