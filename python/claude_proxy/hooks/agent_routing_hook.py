"""
LiteLLM callback for per-agent model routing using prompt fingerprinting.

Detection Algorithm:
1. Verify 2+ system messages (Claude Code pattern)
2. Check first system message contains "Claude Code"
3. Extract second system message content (agent definition)
4. Strip "Notes:" section (dynamic per-request)
5. Compute SHA256[:16] hash as fingerprint
6. Look up in registry for target model

This hook integrates with LiteLLM's callback system via CustomLogger.
"""

import logging
from typing import Any, Optional

from litellm.integrations.custom_logger import CustomLogger

from claude_proxy.registry.agent_hashes import load_registry
from claude_proxy.utils import compute_agent_hash

# Configure module logger
logger = logging.getLogger(__name__)


def extract_system_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract all system messages from the message list."""
    return [m for m in messages if m.get("role") == "system"]


def is_claude_code_request(system_messages: list[dict[str, Any]]) -> bool:
    """
    Check if request is from Claude Code.

    Claude Code pattern: 2+ system messages where first contains "Claude Code".
    """
    if len(system_messages) < 2:
        return False

    first_content = system_messages[0].get("content", "")
    # Handle both string and list content formats
    if isinstance(first_content, list):
        first_content = " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in first_content
        )

    return "Claude Code" in first_content


def extract_agent_hash(system_messages: list[dict[str, Any]]) -> Optional[str]:
    """
    Extract agent prompt hash from system messages.

    Args:
        system_messages: List of system message dictionaries

    Returns:
        SHA256[:16] hash if Claude Code agent pattern detected, None otherwise.
    """
    if not is_claude_code_request(system_messages):
        return None

    # Get second system message (agent definition)
    if len(system_messages) < 2:
        return None

    agent_content = system_messages[1].get("content", "")

    # Handle list content format (for multimodal messages)
    if isinstance(agent_content, list):
        agent_content = " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in agent_content
        )

    if not agent_content:
        return None

    # Use shared hash function (handles Notes: stripping internally)
    return compute_agent_hash(agent_content)


def get_model_for_agent(agent_hash: str) -> Optional[str]:
    """Look up target model for given agent hash."""
    registry = load_registry()
    return registry.get(agent_hash)


class AgentRoutingCallback(CustomLogger):
    """
    LiteLLM CustomLogger callback for agent-based model routing.

    Inspects request messages before sending, extracts agent hash if Claude Code
    pattern is detected, and routes to configured model.
    """

    def __init__(self) -> None:
        """Initialize the agent routing callback."""
        super().__init__()
        # Pre-load registry on init
        load_registry()

    async def async_pre_call_hook(
        self,
        user_api_key_dict: dict,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        """
        LiteLLM async pre-call hook for agent-based model routing.

        This hook is called before each API request is sent.

        Args:
            user_api_key_dict: User API key information
            cache: LiteLLM cache object
            data: Request data dictionary containing model, messages, etc.
            call_type: Type of call (completion, embedding, etc.)

        Returns:
            Modified data dictionary with potentially changed model field
        """
        # Only process completion requests
        if call_type != "completion":
            return data

        messages = data.get("messages", [])

        # Extract system messages
        system_messages = extract_system_messages(messages)

        # Try to extract agent hash
        agent_hash = extract_agent_hash(system_messages)

        if not agent_hash:
            # Not a Claude Code agent request, pass through unchanged
            return data

        # Look up target model in registry
        target_model = get_model_for_agent(agent_hash)

        original_model = data.get("model", "unknown")

        if not target_model:
            # Unknown agent - log for debugging, use original model
            logger.info(
                f"[agent-routing] Unknown agent hash: {agent_hash}, "
                f"keeping model: {original_model}"
            )
            return data

        # Apply routing - change model
        data["model"] = target_model

        # Add metadata for logging/debugging
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["agent_hash"] = agent_hash
        data["metadata"]["routed_from"] = original_model
        data["metadata"]["agent_routed"] = True

        logger.info(
            f"[agent-routing] Agent {agent_hash}: {original_model} -> {target_model}"
        )

        return data

    def log_pre_api_call(
        self,
        model: str,
        messages: list,
        kwargs: dict,
    ) -> None:
        """Synchronous pre-call logging (optional)."""
        pass

    def log_post_api_call(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Log successful API calls with routing metadata."""
        metadata = kwargs.get("metadata", {})
        if metadata.get("agent_routed"):
            agent_hash = metadata.get("agent_hash", "unknown")
            routed_from = metadata.get("routed_from", "unknown")
            model = kwargs.get("model", "unknown")
            logger.debug(
                f"[agent-routing] Completed: agent={agent_hash}, "
                f"from={routed_from}, to={model}"
            )

    def log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Log failed API calls."""
        metadata = kwargs.get("metadata", {})
        if metadata.get("agent_routed"):
            agent_hash = metadata.get("agent_hash", "unknown")
            model = kwargs.get("model", "unknown")
            logger.warning(
                f"[agent-routing] Failed: agent={agent_hash}, model={model}"
            )


# Create singleton callback instance for LiteLLM registration
agent_routing_callback = AgentRoutingCallback()
