"""
claude-proxy - LiteLLM proxy with per-agent model routing and OAuth injection.

A Python-based proxy server using LiteLLM that provides:
- Per-model routing via model aliases (haiku/sonnet/opus)
- Per-agent routing via SHA256 hash-based prompt fingerprinting
- OAuth token injection for Claude API authentication
- API key fallback when OAuth not available
- Configurable fallback chains and retry logic

Usage:
    python -m claude_proxy start
    # or
    claude-proxy start

Environment Variables:
    PROXY_PORT: Port to listen on (default: 4000)
    PROXY_HOST: Host to bind to (default: 0.0.0.0)
    LITELLM_CONFIG: Path to LiteLLM config YAML (default: ./litellm_config.yaml)
    AGENT_REGISTRY_PATH: Path to agent hash registry JSON (default: ./registry/agent_hashes.json)
    CLAUDE_CREDENTIALS_PATH: Path to Claude OAuth credentials (default: /app/.credentials.json)
    ROUTING_CONFIG: Path to routing configuration YAML (default: ./routing_config.yaml)
    DEBUG: Enable verbose logging (default: false)
"""

__version__ = "0.1.0"
__author__ = "fullstacktard"

from .server import main as start_server

__all__ = ["start_server", "__version__"]
