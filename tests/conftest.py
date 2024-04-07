import pytest
from shadeorb.protocol import ORBProtocol


@pytest.fixture
def protocol():
    return ORBProtocol()
