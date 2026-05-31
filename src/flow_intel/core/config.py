"""YAML config loader with env-var substitution. Singleton via get_config()."""
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_config: dict | None = None
_ENV_RE = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _resolve(value: Any) -> Any:
    if isinstance(value, str):
        def replace(m: re.Match) -> str:
            var, default = m.group(1), m.group(2)
            return os.environ.get(var, default if default is not None else m.group(0))
        return _ENV_RE.sub(replace, value)
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    return value


def _load() -> dict:
    root = Path(__file__).parents[3]
    base_path = root / "config" / "base.yaml"
    with open(base_path, encoding="utf-8") as f:
        cfg: dict = yaml.safe_load(f) or {}

    env = os.environ.get("APP_ENV", "")
    if env:
        overlay_path = root / "config" / f"{env}.yaml"
        if overlay_path.exists():
            with open(overlay_path, encoding="utf-8") as f:
                overlay: dict = yaml.safe_load(f) or {}
            cfg = _deep_merge(cfg, overlay)

    return _resolve(cfg)


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def get_config() -> dict:
    global _config
    if _config is None:
        _config = _load()
    return _config
