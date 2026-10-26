import pytest

import lab


@pytest.fixture(scope="session")
def connection():
    with lab.connect() as live_connection:
        yield live_connection


@pytest.fixture
def at_step(connection):
    """Return a function that puts the table in the state after migration N, so each test sets its own stage."""
    return lambda step: lab.reset_to(connection, step)
