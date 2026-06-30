"""Config-driven backend construction — the plug-and-play seam.

Reads models.yaml (pinned model strings per §6) and builds the requested
backend. Add a model = add a profile entry; no code change in the harness.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .backends import ModelBackend

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "models.yaml"


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path) as fh:
        return yaml.safe_load(fh)


def build_backend(profile: str | None = None, config_path: str | Path | None = None) -> ModelBackend:
    cfg = load_config(config_path)
    profiles = cfg.get("profiles", {})
    name = profile or cfg.get("default")
    if name not in profiles:
        raise KeyError(f"unknown profile '{name}'; available: {sorted(profiles)}")

    spec = dict(profiles[name])
    provider = spec.pop("provider")
    spec.pop("note", None)  # documentation only

    if provider == "openai_compat":
        from .backends.openai_compat import OpenAICompatBackend
        return OpenAICompatBackend(**spec)

    if provider == "anthropic":
        try:
            from .backends.anthropic_backend import AnthropicBackend
            return AnthropicBackend(**spec)
        except Exception as e:  # missing SDK creds, etc.
            raise RuntimeError(
                f"anthropic profile '{name}' could not be constructed: {e}. "
                f"Set ANTHROPIC_API_KEY or run `ant auth login` to enable the Claude backend."
            ) from e

    raise ValueError(f"unknown provider '{provider}' in profile '{name}'")
