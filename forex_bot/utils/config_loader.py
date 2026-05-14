"""
FxBot Configuration Loader
===========================
Loads config.yaml and .env, exposes values via dot-notation, and validates
that required environment variables are present.

Usage::

    from forex_bot.utils.config_loader import config

    account_id = config.get("broker.account_id")
    risk       = config.get("risk.risk_per_trade", 0.01)
    pairs      = config.get("pairs")
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from dotenv import load_dotenv
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False

# ---------------------------------------------------------------------------
# Required environment variables - bot will refuse to start if any are absent
# when paper_trading is False.
# ---------------------------------------------------------------------------

REQUIRED_LIVE_ENV_VARS: List[str] = [
    "OANDA_ACCOUNT_ID",
    "OANDA_API_KEY",
]

REQUIRED_PAPER_ENV_VARS: List[str] = [
    "OANDA_ACCOUNT_ID",
    "OANDA_API_KEY",
]

OPTIONAL_ENV_VARS: List[str] = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "EMAIL_SMTP_HOST",
    "EMAIL_SENDER",
    "EMAIL_PASSWORD",
    "EMAIL_RECIPIENT",
    "NEWS_API_KEY",
    "DATABASE_URL",
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _interpolate_env(value: Any) -> Any:
    """
    Recursively replace ``${VAR_NAME}`` placeholders in strings with the
    corresponding environment variable value, or leave the placeholder if
    the variable is not set.
    """
    if isinstance(value, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return _ENV_VAR_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    return value


def _deep_get(data: Dict, key_path: str, default: Any = None) -> Any:
    """
    Retrieve a value from a nested dict using dot-notation key.

    Example::

        _deep_get(cfg, "risk.risk_per_trade")   # -> 0.01
        _deep_get(cfg, "broker.account_id")      # -> "101-..."
    """
    keys = key_path.split(".")
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


# ---------------------------------------------------------------------------
# ConfigLoader class
# ---------------------------------------------------------------------------

class ConfigLoader:
    """
    Singleton that loads ``config.yaml`` and the ``.env`` file, then exposes
    values via :meth:`get`.

    The singleton is accessible via the module-level ``config`` object.
    """

    _instance: Optional["ConfigLoader"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "ConfigLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        config_path: Optional[str] = None,
        env_path: Optional[str] = None,
    ) -> None:
        # Avoid re-initialising the singleton on repeat instantiation
        if getattr(self, "_initialized", False):
            return

        self._raw: Dict[str, Any] = {}
        self._config_path: Optional[str] = None

        self.load_env(env_path)
        if config_path:
            self.load_config(config_path)

        self._initialized = True

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def load_env(self, env_path: Optional[str] = None) -> None:
        """
        Load environment variables from a ``.env`` file.

        Searches in order:
          1. *env_path* argument
          2. ``FOREX_BOT_ENV_FILE`` environment variable
          3. ``.env`` in the same directory as ``config.yaml`` (if known)
          4. ``.env`` in the current working directory

        Does nothing if ``python-dotenv`` is not installed (env vars can
        still be set externally).
        """
        if not _HAS_DOTENV:
            return

        candidates: List[Path] = []
        if env_path:
            candidates.append(Path(env_path))
        if os.environ.get("FOREX_BOT_ENV_FILE"):
            candidates.append(Path(os.environ["FOREX_BOT_ENV_FILE"]))
        # Same directory as config.yaml
        if self._config_path:
            candidates.append(Path(self._config_path).parent / ".env")
        # CWD
        candidates.append(Path.cwd() / ".env")
        # Repo root (two levels up from this file)
        candidates.append(Path(__file__).parent.parent / ".env")

        for candidate in candidates:
            if candidate.is_file():
                load_dotenv(dotenv_path=str(candidate), override=False)
                break

    def load_config(self, path: str) -> None:
        """
        Parse ``config.yaml`` and interpolate environment variable placeholders.

        Args:
            path: Absolute or relative path to ``config.yaml``.

        Raises:
            FileNotFoundError: If *path* does not exist.
            yaml.YAMLError:    If the file contains invalid YAML.
        """
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(
                f"config.yaml not found at: {config_path.resolve()}"
            )

        self._config_path = str(config_path.resolve())

        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        self._raw = _interpolate_env(raw)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a configuration value using dot-notation.

        The key may reference nested YAML sections separated by dots.

        Examples::

            config.get("risk.risk_per_trade")          # -> 0.01
            config.get("broker.environment")           # -> "paper"
            config.get("indicator_params.rsi.period")  # -> 14
            config.get("nonexistent.key", "fallback")  # -> "fallback"

        Args:
            key:     Dot-separated path into the YAML hierarchy.
            default: Value returned when the key is absent. Defaults to None.

        Returns:
            The value at *key* or *default*.
        """
        return _deep_get(self._raw, key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Override a configuration value at runtime (in-memory only).

        Useful for tests or command-line overrides.

        Args:
            key:   Dot-separated path.
            value: New value to store.
        """
        keys = key.split(".")
        target = self._raw
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    def all(self) -> Dict[str, Any]:
        """Return a shallow copy of the entire configuration dictionary."""
        return dict(self._raw)

    def validate(self, live: bool = False) -> List[str]:
        """
        Check that required environment variables are present.

        Args:
            live: If True, apply stricter validation for live-trading mode.

        Returns:
            A list of missing variable names (empty list = all good).
        """
        required = REQUIRED_LIVE_ENV_VARS if live else REQUIRED_PAPER_ENV_VARS
        missing = [var for var in required if not os.environ.get(var)]
        return missing

    def validate_or_raise(self, live: bool = False) -> None:
        """
        Like :meth:`validate` but raises :exc:`EnvironmentError` if any
        required variable is missing.

        Args:
            live: If True, apply stricter validation for live-trading mode.

        Raises:
            EnvironmentError: With a human-readable list of missing variables.
        """
        missing = self.validate(live=live)
        if missing:
            raise EnvironmentError(
                "The following required environment variables are not set:\n"
                + "\n".join(f"  - {v}" for v in missing)
                + "\n\nPlease copy .env.example to .env and fill in the values."
            )

    def is_paper_trading(self) -> bool:
        """
        Return True if the bot is configured for paper (simulated) trading.

        Checks the ``PAPER_TRADING`` environment variable first, then
        ``paper_trading`` in config.yaml.
        """
        env_val = os.environ.get("PAPER_TRADING", "").lower()
        if env_val in ("false", "0", "no"):
            return False
        if env_val in ("true", "1", "yes"):
            return True
        # Fall back to YAML value
        return bool(self._raw.get("paper_trading", True))

    def reload(self) -> None:
        """
        Reload config.yaml from disk (keeps the same path as initial load).
        Useful for hot-reloading configuration without restarting.
        """
        if self._config_path:
            self.load_config(self._config_path)

    def __repr__(self) -> str:
        return (
            f"ConfigLoader(path={self._config_path!r}, "
            f"paper_trading={self.is_paper_trading()})"
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def load_config(path: str) -> ConfigLoader:
    """
    Load (or reload) a config.yaml file into the global singleton.

    Args:
        path: Path to ``config.yaml``.

    Returns:
        The global :class:`ConfigLoader` instance.
    """
    cfg = ConfigLoader()
    cfg.load_config(path)
    return cfg


def load_env(env_path: Optional[str] = None) -> None:
    """
    Load environment variables from *env_path* (or the default ``.env``).

    Delegates to :meth:`ConfigLoader.load_env`.
    """
    ConfigLoader().load_env(env_path)


def _find_default_config() -> Optional[str]:
    """
    Search common locations for ``config.yaml`` and return the first match.

    Checks:
      1. ``FOREX_BOT_CONFIG`` environment variable
      2. ``config.yaml`` in the current working directory
      3. ``config.yaml`` in the ``forex_bot`` package directory
      4. ``config.yaml`` two directory levels up from this file
    """
    env_path = os.environ.get("FOREX_BOT_CONFIG")
    if env_path and Path(env_path).is_file():
        return env_path

    candidates = [
        Path.cwd() / "config.yaml",
        Path(__file__).parent.parent / "config.yaml",
        Path(__file__).parent / "config.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


# ---------------------------------------------------------------------------
# Global singleton instance - auto-loads config.yaml if found
# ---------------------------------------------------------------------------

def _bootstrap() -> ConfigLoader:
    """
    Create and return the global ConfigLoader instance, auto-discovering
    config.yaml if possible.
    """
    instance = ConfigLoader()
    default_cfg = _find_default_config()
    if default_cfg and not instance._raw:
        try:
            instance.load_config(default_cfg)
        except Exception:
            # Don't crash on import; callers can call load_config() manually.
            pass
    return instance


#: Global config singleton. Import this in other modules::
#:
#:     from forex_bot.utils.config_loader import config
#:     value = config.get("risk.risk_per_trade")
config: ConfigLoader = _bootstrap()
