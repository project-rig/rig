"""Create a mock object which returns a future if async=True."""

from mock import Mock
import trollius


def future_mock(return_value=None):  # pramga: no cover
    """Create a mock object which when called returns a future with the
    specified value.
    """
    def side_effect(*args, **kwargs):
        async = kwargs.pop("async", False)
        if async:
            fut = trollius.Future()
            fut.set_result(return_value)
            return fut
        else:
            return return_value

    return Mock(side_effect=side_effect)
