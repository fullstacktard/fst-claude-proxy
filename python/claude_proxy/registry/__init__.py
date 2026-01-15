"""
Agent hash registry for claude-proxy.

Manages the mapping of agent prompt hashes to target models.
The registry is stored in JSON format and loaded on startup.
"""

from claude_proxy.registry.agent_hashes import get_registry, load_registry, reload_registry

__all__ = ["get_registry", "load_registry", "reload_registry"]
