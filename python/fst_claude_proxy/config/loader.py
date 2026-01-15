"""
Configuration loader for fst-claude-proxy.

Loads and validates YAML configuration files for:
- LiteLLM model configuration
- Agent routing rules
- Fallback chains
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

# Configure module logger
logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Loads and manages proxy configuration.

    Configuration files:
    - litellm_config.yaml: LiteLLM model definitions and settings
    - routing_config.yaml: Agent routing rules, fallback chains, retry settings
    """

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        """
        Initialize configuration loader.

        Args:
            config_dir: Base directory for config files (default: parent of this module)
        """
        self.config_dir = config_dir or Path(__file__).parent.parent
        self._litellm_config: Optional[dict[str, Any]] = None
        self._routing_config: Optional[dict[str, Any]] = None

    def load_litellm_config(self) -> dict[str, Any]:
        """
        Load LiteLLM configuration from YAML.

        Returns:
            LiteLLM configuration dictionary
        """
        if self._litellm_config is not None:
            return self._litellm_config

        config_path = os.environ.get(
            "LITELLM_CONFIG", str(self.config_dir / "litellm_config.yaml")
        )

        try:
            with open(config_path) as f:
                self._litellm_config = yaml.safe_load(f) or {}
                logger.info(f"[config] Loaded LiteLLM config from {config_path}")
        except FileNotFoundError:
            logger.warning(f"[config] LiteLLM config not found: {config_path}")
            self._litellm_config = {}
        except yaml.YAMLError as e:
            logger.error(f"[config] Error parsing LiteLLM config: {e}")
            self._litellm_config = {}

        # At this point, _litellm_config is guaranteed to be set
        assert self._litellm_config is not None
        return self._litellm_config

    def load_routing_config(self) -> dict[str, Any]:
        """
        Load routing configuration from YAML.

        Returns:
            Routing configuration dictionary
        """
        if self._routing_config is not None:
            return self._routing_config

        config_path = os.environ.get(
            "ROUTING_CONFIG", str(self.config_dir / "routing_config.yaml")
        )

        try:
            with open(config_path) as f:
                self._routing_config = yaml.safe_load(f) or {}
                logger.info(f"[config] Loaded routing config from {config_path}")
        except FileNotFoundError:
            logger.info(f"[config] Routing config not found: {config_path}")
            self._routing_config = {}
        except yaml.YAMLError as e:
            logger.error(f"[config] Error parsing routing config: {e}")
            self._routing_config = {}

        # At this point, _routing_config is guaranteed to be set
        assert self._routing_config is not None
        return self._routing_config

    def reload(self) -> None:
        """Force reload all configuration files."""
        self._litellm_config = None
        self._routing_config = None
        self.load_litellm_config()
        self.load_routing_config()

    def get_fallback_chain(self, chain_name: str) -> list[str]:
        """
        Get fallback chain by name.

        Args:
            chain_name: Name of the fallback chain

        Returns:
            List of model names in fallback order
        """
        config = self.load_routing_config()
        chains = config.get("fallback_chains", {})
        return chains.get(chain_name, [])

    def get_agent_model(self, agent_name: str) -> Optional[str]:
        """
        Get configured model for agent by name.

        Args:
            agent_name: Name of the agent (e.g., "backend-engineer")

        Returns:
            Target model name or None if not configured
        """
        config = self.load_routing_config()
        agent_routing = config.get("agent_routing", {})
        return agent_routing.get(agent_name)

    def get_default_model(self) -> str:
        """
        Get default model when no routing matches.

        Returns:
            Default model name (defaults to "sonnet")
        """
        config = self.load_routing_config()
        return config.get("default_model", "sonnet")

    def get_retry_config(self) -> dict[str, Any]:
        """
        Get retry configuration.

        Returns:
            Dictionary with max_retries, retry_delay_seconds, exponential_backoff
        """
        config = self.load_routing_config()
        return config.get(
            "retry",
            {
                "max_retries": 3,
                "retry_delay_seconds": 1,
                "exponential_backoff": True,
            },
        )

    def get_rate_limits(self, provider: str) -> Optional[dict[str, int]]:
        """
        Get rate limit configuration for a provider.

        Args:
            provider: Provider name (e.g., "anthropic", "openai")

        Returns:
            Dictionary with requests_per_minute, tokens_per_minute or None
        """
        config = self.load_routing_config()
        rate_limits = config.get("rate_limits", {})
        return rate_limits.get(provider)


# Singleton instance
_config_loader: Optional[ConfigLoader] = None


def get_config() -> ConfigLoader:
    """
    Get or create config loader singleton.

    Returns:
        ConfigLoader instance
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader
