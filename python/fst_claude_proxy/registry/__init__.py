"""
Agent hash registry for fst-claude-proxy.

Manages the mapping of agent prompt hashes to target models.
The registry is stored in JSON format and loaded on startup.
"""

from fst_claude_proxy.registry.agent_hashes import get_registry, load_registry, reload_registry

__all__ = ["get_registry", "load_registry", "reload_registry"]
