"""Exceptions raised by mplxe.

Note: by design, normalization itself never raises. Errors here are reserved
for configuration and rule-construction problems detected at load time.
Anything that goes wrong at normalize time becomes a `warning` on the
NormalizeResult instead.
"""


class MplxeError(Exception):
    """Base exception for mplxe."""


class ConfigError(MplxeError):
    """Raised when configuration (e.g., YAML) is invalid."""


class RuleError(MplxeError):
    """Raised when a rule cannot be parsed or compiled."""
