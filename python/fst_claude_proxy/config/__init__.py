"""
Configuration management for fst-claude-proxy.

Provides YAML-based configuration loading and validation for:
- LiteLLM model configuration
- Agent routing rules
- Fallback chains
"""

from fst_claude_proxy.config.loader import ConfigLoader, get_config

__all__ = ["ConfigLoader", "get_config"]
