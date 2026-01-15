"""
Agent hash registry management for claude-proxy.

Provides functions to load, access, and reload the agent hash registry.
The registry maps agent prompt hashes to target model names.

Registry Format (agent_hashes.json):
{
  "mappings": {
    "a3f8b2c1d4e5f6g7": "opus",
    "7d4e9f5a2b1c3d4e": "sonnet",
    "b1c2d3e4f5a6g7h8": "haiku"
  },
  "metadata": {
    "description": "Agent hash to model routing table",
    "updated_at": "2025-01-09T00:00:00Z",
    "version": "1.0.0"
  }
}
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

# Configure module logger
logger = logging.getLogger(__name__)

# Registry cache
_AGENT_REGISTRY: dict[str, str] = {}
_REGISTRY_LOADED = False
_REGISTRY_PATH: Optional[str] = None


def _get_registry_path() -> str:
    """Get the path to the agent hash registry file."""
    global _REGISTRY_PATH
    if _REGISTRY_PATH is None:
        _REGISTRY_PATH = os.environ.get(
            "AGENT_REGISTRY_PATH",
            str(Path(__file__).parent / "agent_hashes.json"),
        )
    return _REGISTRY_PATH


def load_registry() -> dict[str, str]:
    """
    Load agent hash to model mappings from JSON file.

    Returns:
        Dictionary mapping agent hashes to model names
    """
    global _AGENT_REGISTRY, _REGISTRY_LOADED

    if _REGISTRY_LOADED:
        return _AGENT_REGISTRY

    registry_path = _get_registry_path()

    try:
        with open(registry_path) as f:
            data = json.load(f)
            _AGENT_REGISTRY = data.get("mappings", {})
            _REGISTRY_LOADED = True
            logger.info(
                f"[registry] Loaded {len(_AGENT_REGISTRY)} agent mappings "
                f"from {registry_path}"
            )
    except FileNotFoundError:
        logger.warning(
            f"[registry] No registry at {registry_path}, using empty registry"
        )
        _AGENT_REGISTRY = {}
        _REGISTRY_LOADED = True
    except json.JSONDecodeError as e:
        logger.error(f"[registry] Error parsing registry: {e}")
        _AGENT_REGISTRY = {}
        _REGISTRY_LOADED = True

    return _AGENT_REGISTRY


def reload_registry() -> dict[str, str]:
    """
    Force reload of agent registry from disk.

    Returns:
        Freshly loaded registry dictionary
    """
    global _REGISTRY_LOADED
    _REGISTRY_LOADED = False
    return load_registry()


def get_registry() -> dict[str, str]:
    """
    Get the current agent registry.

    Loads from disk if not already loaded.

    Returns:
        Dictionary mapping agent hashes to model names
    """
    return load_registry()


def get_model_for_hash(agent_hash: str) -> Optional[str]:
    """
    Look up target model for a given agent hash.

    Args:
        agent_hash: SHA256[:16] hash of agent prompt

    Returns:
        Target model name or None if not found
    """
    registry = get_registry()
    return registry.get(agent_hash)
