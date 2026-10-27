"""Startup shared by the programs: settings or a clear exit code 2."""

from __future__ import annotations

import os
import sys

from ..domain.host import HostLoad
from ..infrastructure.logging import configure_logging
from ..infrastructure.settings import ConfigurationError, Settings


def load_settings() -> Settings | None:
    """Read and validate the environment, configure logging, or print the problem and return None."""
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return None
    configure_logging(settings.log_level)
    return settings


def measure_host_load() -> HostLoad:
    """The 1-minute load average and CPU count right now, so results can say how busy the machine was."""
    return HostLoad(os.getloadavg()[0], os.cpu_count() or 1)
