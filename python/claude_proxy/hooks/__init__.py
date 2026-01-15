"""
LiteLLM hooks for claude-proxy.

This module provides custom hooks for request modification:
- agent_routing_hook: Per-agent model routing based on prompt fingerprinting
- oauth_hook: OAuth token injection for Claude API authentication
"""

from claude_proxy.hooks.agent_routing_hook import agent_routing_callback
from claude_proxy.hooks.oauth_hook import invalidate_credential_cache, oauth_injection_callback

__all__ = ["agent_routing_callback", "oauth_injection_callback", "invalidate_credential_cache"]
