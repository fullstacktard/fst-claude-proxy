"""
LiteLLM callback for OAuth token injection.

Reads Claude OAuth credentials from mounted credentials file and injects
Authorization header for requests to Anthropic API.

Token Structure (from ~/.claude/.credentials.json):
{
  "claudeAiOauth": {
    "accessToken": "...",
    "refreshToken": "...",
    "expiresAt": 1234567890,
    "rateLimitTier": "claude_pro_2025_04",
    "scopes": ["..."],
    "subscriptionType": "..."
  }
}

The token refresh is handled externally by account-manager.ts or similar.
This hook simply reads the latest credentials from the mounted file.
"""

import json
import logging
import os
import time
from typing import Any, Optional

from litellm.integrations.custom_logger import CustomLogger

# Configure module logger
logger = logging.getLogger(__name__)

# Credential cache
_OAUTH_TOKEN: Optional[dict[str, Any]] = None
_LAST_LOAD_TIME: float = 0
_CACHE_TTL_SECONDS: float = 60.0  # Reload credentials every 60 seconds

# Default credentials path (can be overridden via environment)
_DEFAULT_CREDENTIALS_PATH = "/app/.credentials.json"


def _get_credentials_path() -> str:
    """Get the path to the Claude credentials file."""
    return os.environ.get("CLAUDE_CREDENTIALS_PATH", _DEFAULT_CREDENTIALS_PATH)


def load_oauth_credentials(force: bool = False) -> Optional[dict[str, Any]]:
    """
    Load OAuth credentials from credentials file.

    Args:
        force: Force reload even if cache is valid

    Returns:
        OAuth token dictionary or None if not available
    """
    global _OAUTH_TOKEN, _LAST_LOAD_TIME

    current_time = time.time()

    # Check cache validity
    if (
        not force
        and _OAUTH_TOKEN is not None
        and (current_time - _LAST_LOAD_TIME) < _CACHE_TTL_SECONDS
    ):
        return _OAUTH_TOKEN

    credentials_path = _get_credentials_path()

    try:
        with open(credentials_path) as f:
            data = json.load(f)
            _OAUTH_TOKEN = data.get("claudeAiOauth")
            _LAST_LOAD_TIME = current_time

            if _OAUTH_TOKEN:
                expires_at = _OAUTH_TOKEN.get("expiresAt", 0)
                logger.debug(
                    f"[oauth] Loaded credentials from {credentials_path}, "
                    f"expires at: {expires_at}"
                )
            return _OAUTH_TOKEN
    except FileNotFoundError:
        logger.debug(f"[oauth] Credentials file not found: {credentials_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[oauth] Error parsing credentials: {e}")
        return None
    except (OSError, PermissionError) as e:
        logger.error(f"[oauth] Error reading credentials file: {e}")
        return None


def is_token_expired(token: dict[str, Any], buffer_seconds: int = 300) -> bool:
    """
    Check if OAuth token is expired.

    Args:
        token: OAuth token dictionary
        buffer_seconds: Safety buffer before expiration (default: 5 minutes)

    Returns:
        True if token is expired or will expire within buffer period
    """
    expires_at = token.get("expiresAt", 0)
    # expiresAt is in milliseconds, convert to seconds if needed
    if expires_at > 1e12:  # Timestamp is in milliseconds
        expires_at = expires_at / 1000

    return time.time() > (expires_at - buffer_seconds)


def get_access_token() -> Optional[str]:
    """
    Get valid OAuth access token, refreshing cache if needed.

    Returns:
        Access token string or None if not available
    """
    token = load_oauth_credentials()

    if token is None:
        return None

    if is_token_expired(token):
        logger.info("[oauth] Token expired, force reloading credentials...")
        # Force reload from file (account-manager handles refresh)
        token = load_oauth_credentials(force=True)

        if token is None or is_token_expired(token):
            logger.warning("[oauth] Token still expired after reload")
            return None

    return token.get("accessToken")


def invalidate_credential_cache() -> dict[str, Any]:
    """
    Invalidate the OAuth credential cache immediately.

    This forces the next request to reload credentials from disk,
    enabling immediate use of newly synced credentials.

    Returns:
        Dictionary with success status and message
    """
    global _OAUTH_TOKEN, _LAST_LOAD_TIME

    _OAUTH_TOKEN = None
    _LAST_LOAD_TIME = 0

    logger.info("[oauth] Credential cache invalidated")

    return {
        "success": True,
        "message": "Credential cache invalidated"
    }


def is_anthropic_request(data: dict[str, Any]) -> bool:
    """
    Check if request is targeting Anthropic API.

    Args:
        data: Request data dictionary

    Returns:
        True if this is an Anthropic/Claude request
    """
    model = data.get("model", "").lower()
    # Check for Claude model names
    return "claude" in model or "anthropic" in model


class OAuthInjectionCallback(CustomLogger):
    """
    LiteLLM CustomLogger callback for OAuth token injection.

    Adds Authorization header with OAuth bearer token for Anthropic requests
    when credentials are available.
    """

    def __init__(self) -> None:
        """Initialize the OAuth injection callback."""
        super().__init__()
        # Attempt to load credentials on init
        creds = load_oauth_credentials()
        if creds:
            logger.info("[oauth] OAuth credentials available")
        else:
            logger.info("[oauth] No OAuth credentials found, will use API key fallback")

    async def async_pre_call_hook(
        self,
        user_api_key_dict: dict,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        """
        LiteLLM async pre-call hook for OAuth token injection.

        Adds Authorization header with OAuth bearer token for Anthropic requests.

        Args:
            user_api_key_dict: User API key information
            cache: LiteLLM cache object
            data: Request data dictionary
            call_type: Type of call (completion, embedding, etc.)

        Returns:
            Modified data dictionary with OAuth token header if available
        """
        # Only process completion requests
        if call_type != "completion":
            return data

        # Only inject OAuth for Anthropic requests
        if not is_anthropic_request(data):
            return data

        # Get OAuth token
        access_token = get_access_token()

        if not access_token:
            # No OAuth available, let LiteLLM use API key fallback
            logger.debug("[oauth] No OAuth token available, using API key fallback")
            return data

        # Inject Authorization header
        # Note: For LiteLLM, we need to use extra_headers for custom headers
        if "extra_headers" not in data:
            data["extra_headers"] = {}

        data["extra_headers"]["Authorization"] = f"Bearer {access_token}"

        # Add metadata for logging
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["oauth_injected"] = True

        logger.debug("[oauth] Injected OAuth token for Anthropic request")

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
        """Log successful API calls with OAuth metadata."""
        metadata = kwargs.get("metadata", {})
        if metadata.get("oauth_injected"):
            model = kwargs.get("model", "unknown")
            logger.debug(f"[oauth] Completed request to {model} with OAuth")

    def log_failure_event(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
    ) -> None:
        """Log failed API calls."""
        metadata = kwargs.get("metadata", {})
        if metadata.get("oauth_injected"):
            model = kwargs.get("model", "unknown")
            logger.warning(f"[oauth] Failed OAuth request to {model}")


# Create singleton callback instance for LiteLLM registration
oauth_injection_callback = OAuthInjectionCallback()
