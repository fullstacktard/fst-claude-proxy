"""
Combined callbacks for claude-proxy.

This module exports a single CustomLogger instance that handles:
- Agent routing (per-agent model selection)
- OAuth token injection for Claude models
- Custom API endpoint for credential cache invalidation

LiteLLM loads this via: callbacks: hooks.callbacks.proxy_callbacks
"""

from litellm.integrations.custom_logger import CustomLogger
import logging
import os
import json
import hashlib
import platform
import uuid
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Claude Code identification headers - REQUIRED for OAuth to work
# Anthropic validates that OAuth requests match Claude Code's request signature
CLAUDE_CODE_VERSION = "2.1.5"
CLAUDE_CODE_USER_AGENT = f"claude-cli/{CLAUDE_CODE_VERSION} (external, cli)"
# Beta headers must match what Claude Code sends
CLAUDE_CODE_BETA_HEADERS = "oauth-2025-04-20,interleaved-thinking-2025-05-14,prompt-caching-2024-07-31,max-tokens-3-5-sonnet-2024-07-15,pdfs-2024-09-25,token-efficient-tools-2025-02-19"

# Z-AI model mapping (zai-* prefix to actual Anthropic model names)
ZAI_MODEL_MAP = {
    "zai-haiku": "anthropic/claude-3-5-haiku-20241022",
    "zai-sonnet": "anthropic/claude-sonnet-4-20250514",
    "zai-opus": "anthropic/claude-opus-4-5-20251101",
}

# Model alias mapping (registry model names to Anthropic model IDs)
MODEL_ALIAS_MAP = {
    "haiku": "claude-3-5-haiku-20241022",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-5-20251101",
}

# Z-AI API configuration
ZAI_API_BASE = "https://api.z.ai/api/anthropic"

# OAuth credential cache (module-level for invalidation endpoint)
_OAUTH_TOKEN_CACHE: Optional[str] = None
_OAUTH_USER_ID_CACHE: Optional[str] = None
_OAUTH_ACCOUNT_UUID_CACHE: Optional[str] = None
_OAUTH_CACHE_TIME: float = 0
_OAUTH_CACHE_TTL: float = 60.0  # seconds
_SESSION_ID: str = str(uuid.uuid4())[:8]  # Session ID for metadata

# Load agent registry
AGENT_REGISTRY_PATH = os.environ.get(
    "AGENT_REGISTRY_PATH",
    "/app/registry/agent_hashes.json"
)

# Load Claude credentials path
CLAUDE_CREDENTIALS_PATH = os.environ.get(
    "CLAUDE_CREDENTIALS_PATH",
    "/app/.credentials.json"
)


def load_agent_registry() -> Dict[str, str]:
    """Load agent hash to model mappings."""
    try:
        if os.path.exists(AGENT_REGISTRY_PATH):
            with open(AGENT_REGISTRY_PATH, "r") as f:
                data = json.load(f)
                # Handle multiple formats:
                # 1. {mappings: {hash: model}} - new format with metadata
                # 2. {agents: [{hash, model}]} - old array format
                # 3. {hash: model} - direct mapping format
                if isinstance(data, dict):
                    if "mappings" in data:
                        return data["mappings"]
                    if "agents" in data:
                        return {a["hash"]: a.get("model", "sonnet") for a in data["agents"]}
                return data
    except Exception as e:
        logger.warning(f"[callbacks] Failed to load agent registry: {e}")
    return {}


def load_oauth_credentials(force: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Load OAuth credentials from Claude credentials file with caching.

    Returns:
        Tuple of (access_token, user_id, account_uuid)
    """
    global _OAUTH_TOKEN_CACHE, _OAUTH_USER_ID_CACHE, _OAUTH_ACCOUNT_UUID_CACHE, _OAUTH_CACHE_TIME

    import time
    current_time = time.time()

    # Check cache validity
    if (
        not force
        and _OAUTH_TOKEN_CACHE is not None
        and (current_time - _OAUTH_CACHE_TIME) < _OAUTH_CACHE_TTL
    ):
        return _OAUTH_TOKEN_CACHE, _OAUTH_USER_ID_CACHE, _OAUTH_ACCOUNT_UUID_CACHE

    token = None
    user_id = None
    account_uuid = None

    try:
        # Load OAuth token from .credentials.json
        if os.path.exists(CLAUDE_CREDENTIALS_PATH):
            with open(CLAUDE_CREDENTIALS_PATH, "r") as f:
                creds = json.load(f)
                oauth_data = creds.get("claudeAiOauth", creds)
                token = oauth_data.get("accessToken")

        # Load user_id and account_uuid from ~/.claude.json (Claude Code's main config)
        # This is where Claude Code stores oauthAccount info
        claude_json_path = os.path.expanduser("~/.claude.json")
        # In container, check /root/.claude.json as well
        if not os.path.exists(claude_json_path):
            claude_json_path = "/root/.claude.json"
        # Also check mounted path
        if not os.path.exists(claude_json_path):
            claude_json_path = "/app/.claude.json"

        if os.path.exists(claude_json_path):
            with open(claude_json_path, "r") as f:
                claude_config = json.load(f)
                # userID is the main user identifier
                user_id = claude_config.get("userID")
                # oauthAccount contains accountUuid
                oauth_account = claude_config.get("oauthAccount", {})
                account_uuid = oauth_account.get("accountUuid")

        # Fallback to credentials file if not found
        if not user_id and os.path.exists(CLAUDE_CREDENTIALS_PATH):
            with open(CLAUDE_CREDENTIALS_PATH, "r") as f:
                creds = json.load(f)
                oauth_data = creds.get("claudeAiOauth", creds)
                user_id = oauth_data.get("userId") or creds.get("userId")
                account_uuid = account_uuid or oauth_data.get("accountUuid") or creds.get("accountUuid")

        # Generate placeholder IDs if not present
        if not user_id:
            user_id = "anonymous"
        if not account_uuid:
            account_uuid = "default"

        if token:
            _OAUTH_TOKEN_CACHE = token
            _OAUTH_USER_ID_CACHE = user_id
            _OAUTH_ACCOUNT_UUID_CACHE = account_uuid
            _OAUTH_CACHE_TIME = current_time
            print(f"[callbacks] OAuth credentials loaded: user_id={user_id[:20] if user_id else 'None'}..., account_uuid={account_uuid}", flush=True)
        return token, user_id, account_uuid
    except Exception as e:
        logger.warning(f"[callbacks] Failed to load OAuth credentials: {e}")
    return None, None, None


def load_oauth_token(force: bool = False) -> Optional[str]:
    """Load OAuth token from Claude credentials file with caching (legacy wrapper)."""
    token, _, _ = load_oauth_credentials(force)
    return token


def invalidate_credential_cache() -> Dict[str, Any]:
    """
    Invalidate the OAuth credential cache immediately.

    This forces the next request to reload credentials from disk,
    enabling immediate use of newly synced credentials.

    Returns:
        Dictionary with success status and message
    """
    global _OAUTH_TOKEN_CACHE, _OAUTH_CACHE_TIME

    _OAUTH_TOKEN_CACHE = None
    _OAUTH_CACHE_TIME = 0

    logger.info("[callbacks] Credential cache invalidated")

    return {
        "success": True,
        "message": "Credential cache invalidated"
    }


def compute_agent_hash(system_prompt) -> str:
    """Compute SHA256 hash of system prompt (first 16 chars).

    Args:
        system_prompt: Either a string or a list of content blocks
    """
    # Handle content blocks format (list of {"type": "text", "text": "..."})
    if isinstance(system_prompt, list):
        system_prompt = " ".join(
            block.get("text", "") for block in system_prompt
            if isinstance(block, dict) and block.get("type") == "text"
        )

    # Ensure we have a string
    if not isinstance(system_prompt, str):
        system_prompt = str(system_prompt) if system_prompt else ""

    # Remove Notes: section if present
    if "Notes:" in system_prompt:
        system_prompt = system_prompt.split("Notes:")[0]
    return hashlib.sha256(system_prompt.encode()).hexdigest()[:16]


def extract_system_prompt(messages: list) -> Optional[str]:
    """
    Extract system prompt from messages array.

    Handles both:
    - OpenAI format: {"role": "system", "content": "..."}
    - Anthropic format: {"system": "..."} at top level (handled separately)
    """
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # Handle content blocks
                return " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
    return None


def determine_routing(
    body: Dict[str, Any],
    agent_registry: Dict[str, str]
) -> Tuple[str, str, Optional[str]]:
    """
    Determine routing based on agent hash matching.

    Args:
        body: Request body (Anthropic Messages API format)
        agent_registry: Hash to model mapping

    Returns:
        Tuple of (api_base_url, model_to_use, api_key_or_none)
        - For Z-AI: ("https://api.z.ai/api/anthropic", "anthropic/claude-...", ZAI_API_KEY)
        - For OAuth: ("https://api.anthropic.com/v1/messages", "claude-...", None)
    """
    # Default routing: OAuth to Anthropic
    default_api_base = "https://api.anthropic.com/v1/messages"
    original_model = body.get("model", "claude-sonnet-4-20250514")

    # Extract system prompt for hash computation
    # Anthropic format: "system" field at top level
    system_prompt = body.get("system")

    # Also check messages array for OpenAI-style system messages
    if not system_prompt:
        messages = body.get("messages", [])
        system_prompt = extract_system_prompt(messages)

    if not system_prompt or not agent_registry:
        logger.debug(f"[routing] No system prompt or registry, using default: {original_model}")
        return default_api_base, original_model, None

    # Compute hash and check registry
    agent_hash = compute_agent_hash(system_prompt)

    if agent_hash not in agent_registry:
        logger.debug(f"[routing] Hash {agent_hash[:8]}... not in registry, using default: {original_model}")
        return default_api_base, original_model, None

    # Found match - get target model alias
    target_alias = agent_registry[agent_hash]
    logger.info(f"[routing] Agent match: {agent_hash[:8]}... -> {target_alias}")

    # Check if this is a Z-AI routed model (prefixed with zai-)
    if target_alias.startswith("zai-"):
        # Route to Z-AI
        zai_api_key = os.environ.get("ZAI_API_KEY")
        if not zai_api_key:
            logger.warning(f"[routing] ZAI_API_KEY not set, falling back to OAuth for {target_alias}")
            # Fall back to OAuth with standard model
            standard_alias = target_alias.replace("zai-", "")
            resolved_model = MODEL_ALIAS_MAP.get(standard_alias, original_model)
            return default_api_base, resolved_model, None

        # Resolve Z-AI model name
        resolved_model = ZAI_MODEL_MAP.get(target_alias)
        if not resolved_model:
            logger.warning(f"[routing] Unknown Z-AI model {target_alias}, using default")
            return default_api_base, original_model, None

        logger.info(f"[routing] Z-AI route: {target_alias} -> {resolved_model}")
        return ZAI_API_BASE, resolved_model, zai_api_key

    # Standard model alias (opus, sonnet, haiku) - use OAuth
    resolved_model = MODEL_ALIAS_MAP.get(target_alias, original_model)
    logger.info(f"[routing] OAuth route: {target_alias} -> {resolved_model}")
    return default_api_base, resolved_model, None


class ClaudeProxyCallbacks(CustomLogger):
    """
    Combined callback handler for claude-proxy.

    Implements:
    - async_pre_call_hook: Modifies requests before they're sent
      - Agent routing: Maps agent hash to target model
      - OAuth injection: Adds OAuth token for Claude models
    """

    def __init__(self):
        super().__init__()
        self.agent_registry = load_agent_registry()
        logger.info(f"[callbacks] Loaded {len(self.agent_registry)} agent mappings")

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Dict[str, Any],
        cache: Any,
        data: Dict[str, Any],
        call_type: str
    ) -> Dict[str, Any]:
        """
        Called before each LiteLLM completion call.

        Modifies request data for:
        1. Agent routing - check system prompt hash, route to configured model
        2. OAuth injection - add OAuth token and Claude Code headers for Anthropic models

        OAuth Implementation Notes (from Crush/ccproxy research):
        - Anthropic validates OAuth requests match Claude Code's exact signature
        - Must include: user-agent, x-app, anthropic-beta, Stainless headers
        - Must NOT include x-api-key header (conflicts with OAuth)
        - Must include metadata.user_id in request body
        """
        logger.info(f"[callbacks] async_pre_call_hook called for model={data.get('model')}")
        try:
            # Extract system prompt for agent routing
            messages = data.get("messages", [])
            system_prompt = None

            for msg in messages:
                if msg.get("role") == "system":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        system_prompt = content
                    elif isinstance(content, list):
                        # Handle content blocks
                        system_prompt = " ".join(
                            block.get("text", "") for block in content
                            if isinstance(block, dict) and block.get("type") == "text"
                        )
                    break

            # Agent routing
            if system_prompt and self.agent_registry:
                agent_hash = compute_agent_hash(system_prompt)
                if agent_hash in self.agent_registry:
                    target_model = self.agent_registry[agent_hash]
                    logger.info(f"[callbacks] Agent routing: {agent_hash[:8]}... -> {target_model}")
                    data["model"] = target_model

            # OAuth injection for Claude models (direct Anthropic API only)
            model = data.get("model", "")
            is_claude_model = "claude" in model.lower() or "anthropic" in model.lower()
            # Skip OAuth for z-ai or other alternative providers
            is_direct_anthropic = not any(prefix in model.lower() for prefix in ["zai-", "openai/", "gpt-"])

            if is_claude_model and is_direct_anthropic:
                oauth_token, user_id, account_uuid = load_oauth_credentials()
                if oauth_token:
                    # Initialize extra_headers if not present
                    if "extra_headers" not in data:
                        data["extra_headers"] = {}

                    # ===== CRITICAL: Claude Code Identification Headers =====
                    # Anthropic validates OAuth requests match Claude Code's signature
                    # Reference: Crush v0.19.0, ccproxy, Claude Code CHANGELOG

                    # 1. User-Agent - Must match Claude Code exactly
                    data["extra_headers"]["user-agent"] = CLAUDE_CODE_USER_AGENT

                    # 2. App identifier
                    data["extra_headers"]["x-app"] = "cli"

                    # 3. Browser access flag (required for OAuth)
                    data["extra_headers"]["anthropic-dangerous-direct-browser-access"] = "true"

                    # 4. Beta features header - CRITICAL for OAuth
                    data["extra_headers"]["anthropic-beta"] = CLAUDE_CODE_BETA_HEADERS

                    # ===== Stainless SDK Headers =====
                    # These headers are added by the Anthropic SDK and validated
                    data["extra_headers"]["x-stainless-arch"] = platform.machine() or "unknown"
                    data["extra_headers"]["x-stainless-lang"] = "js"
                    data["extra_headers"]["x-stainless-os"] = platform.system().lower() or "unknown"
                    data["extra_headers"]["x-stainless-package-version"] = CLAUDE_CODE_VERSION
                    data["extra_headers"]["x-stainless-retry-count"] = "0"
                    data["extra_headers"]["x-stainless-runtime"] = "node"
                    data["extra_headers"]["x-stainless-runtime-version"] = "v22.0.0"

                    # ===== OAuth Token =====
                    # Set as Authorization header via api_key (LiteLLM handles the Bearer prefix)
                    data["api_key"] = oauth_token

                    # ===== Request Body: metadata.user_id =====
                    # Required for OAuth - identifies the user making the request
                    metadata_user_id = f"user_{user_id}_account_{account_uuid}_session_{_SESSION_ID}"
                    if "metadata" not in data:
                        data["metadata"] = {}
                    data["metadata"]["user_id"] = metadata_user_id

                    logger.info(f"[callbacks] Injected OAuth token + Claude Code headers for: {model}")
                    logger.debug(f"[callbacks] metadata.user_id: {metadata_user_id}")

        except Exception as e:
            logger.error(f"[callbacks] Error in pre_call_hook: {e}")

        return data

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        """Log successful API calls."""
        model = kwargs.get("model", "unknown")
        logger.debug(f"[callbacks] Success: {model}")

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        """Log failed API calls."""
        model = kwargs.get("model", "unknown")
        error = kwargs.get("exception", "unknown error")
        logger.warning(f"[callbacks] Failure: {model} - {error}")


# Export the callback instance for LiteLLM to load
proxy_callbacks = ClaudeProxyCallbacks()


# Shared handler for /v1/messages requests (used by both middleware and endpoint)
async def _handle_messages_request(request_body: bytes, request_headers: dict = None):
    """
    Handle /v1/messages request with OAuth injection and agent routing.

    This is the core handler extracted so it can be called from middleware.
    Returns a tuple of (response_data, status_code, is_streaming, headers).

    Args:
        request_body: The raw request body bytes
        request_headers: Optional headers from the original request (for forwarding)
    """
    from fastapi.responses import StreamingResponse, JSONResponse
    import httpx

    # Log incoming headers for debugging
    if request_headers:
        print(f"[callbacks] Incoming request headers: {request_headers}", flush=True)

    try:
        body = json.loads(request_body)
        original_model = body.get("model", "claude-sonnet-4-20250514")
        print(f"[callbacks] Parsed request body, model={original_model}", flush=True)

        # DEBUG: Log system prompt to understand what Claude Code sends
        system = body.get("system", "NO SYSTEM PROMPT")
        if isinstance(system, list) and len(system) > 0:
            first_block = system[0] if system else {}
            print(f"[callbacks] DEBUG system prompt (first 200 chars): {str(first_block)[:200]}", flush=True)
        elif isinstance(system, str):
            print(f"[callbacks] DEBUG system prompt (first 200 chars): {system[:200]}", flush=True)

        # ===== AGENT ROUTING =====
        try:
            api_base, resolved_model, zai_api_key = determine_routing(
                body, proxy_callbacks.agent_registry
            )
        except Exception as routing_error:
            print(f"[callbacks] Routing error: {routing_error}", flush=True)
            # Default to Anthropic without routing
            api_base = "https://api.anthropic.com/v1/messages"
            resolved_model = original_model
            zai_api_key = None

        body["model"] = resolved_model
        is_zai_route = zai_api_key is not None
        print(f"[callbacks] Routing complete: api_base={api_base}, model={resolved_model}, zai={is_zai_route}", flush=True)

        if is_zai_route:
            logger.info(f"[callbacks] Z-AI route: {original_model} -> {resolved_model} via {api_base}")
            headers = {
                "x-api-key": zai_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            api_url = f"{api_base}/v1/messages"
        else:
            print(f"[callbacks] OAuth route: {original_model} -> {resolved_model}", flush=True)

            # Strategy: ALWAYS use our own credentials from the credentials file
            # This enables the account switching system to work properly
            # We ignore any OAuth token that Claude Code sends and replace it with ours
            headers = {}

            # Load OAuth credentials from our credentials file (supports account switching)
            oauth_token, user_id, account_uuid = load_oauth_credentials()
            if not oauth_token:
                print("[callbacks] No OAuth token available in credentials file, returning 401", flush=True)
                return JSONResponse(
                    status_code=401,
                    content={"error": {"message": "OAuth token not available. Run account sync first.", "type": "authentication_error"}}
                )
            print(f"[callbacks] Using OAuth token from credentials file (account: {account_uuid})", flush=True)

            # Forward identifying headers from original request (but NOT authorization)
            # These headers make Anthropic believe the request comes from Claude Code
            if request_headers:
                forward_headers = [
                    # DO NOT forward "authorization" - we use our own token
                    "user-agent", "x-app", "anthropic-beta",
                    "anthropic-dangerous-direct-browser-access",
                    "anthropic-version",
                    "x-stainless-arch", "x-stainless-lang", "x-stainless-os",
                    "x-stainless-package-version", "x-stainless-retry-count",
                    "x-stainless-runtime", "x-stainless-runtime-version",
                    "x-stainless-timeout"
                ]
                for h in forward_headers:
                    if h in request_headers:
                        headers[h] = request_headers[h]

            # Set OUR OAuth token (from credentials file, not from Claude Code's request)
            headers["authorization"] = f"Bearer {oauth_token}"
            headers["anthropic-version"] = request_headers.get("anthropic-version", "2023-06-01") if request_headers else "2023-06-01"
            headers["content-type"] = "application/json"
            headers["accept"] = "application/json"  # Claude Code sends this

            # CRITICAL: Ensure oauth-2025-04-20 beta header is present
            # Without this, Anthropic returns "OAuth authentication is currently not supported"
            existing_beta = headers.get("anthropic-beta", "")
            if "oauth-2025-04-20" not in existing_beta:
                if existing_beta:
                    headers["anthropic-beta"] = f"oauth-2025-04-20,{existing_beta}"
                else:
                    headers["anthropic-beta"] = "oauth-2025-04-20"
                print(f"[callbacks] Added oauth-2025-04-20 to anthropic-beta header", flush=True)

            # ===== Request body normalization to match Claude Code =====
            # CRITICAL: Anthropic validates that the system prompt starts with
            # "You are Claude Code, Anthropic's official CLI for Claude."
            # Claude Code sends this automatically, but non-Claude-Code clients need it injected.

            CLAUDE_CODE_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."

            system_prompt = body.get("system")
            needs_injection = False

            if not system_prompt:
                # No system prompt at all - inject one
                needs_injection = True
            elif isinstance(system_prompt, list):
                # Check if first block starts with Claude Code identifier
                if len(system_prompt) == 0:
                    needs_injection = True
                else:
                    first_block = system_prompt[0]
                    if isinstance(first_block, dict):
                        text = first_block.get("text", "")
                        if not text.startswith(CLAUDE_CODE_SYSTEM_PREFIX):
                            needs_injection = True
                    else:
                        needs_injection = True
            elif isinstance(system_prompt, str):
                if not system_prompt.startswith(CLAUDE_CODE_SYSTEM_PREFIX):
                    needs_injection = True

            if needs_injection:
                print("[callbacks] Injecting Claude Code system prompt prefix", flush=True)
                claude_code_block = {
                    "type": "text",
                    "text": CLAUDE_CODE_SYSTEM_PREFIX,
                    "cache_control": {"type": "ephemeral"}
                }
                if not system_prompt:
                    body["system"] = [claude_code_block]
                elif isinstance(system_prompt, list):
                    body["system"] = [claude_code_block] + system_prompt
                elif isinstance(system_prompt, str):
                    body["system"] = [claude_code_block, {"type": "text", "text": system_prompt}]

            # Claude Code always includes empty tools array if none specified
            if "tools" not in body:
                body["tools"] = []
            # Claude Code doesn't send temperature
            if "temperature" in body:
                del body["temperature"]

            # ===== CRITICAL: Inject metadata.user_id =====
            # Anthropic requires metadata.user_id for OAuth requests
            # This must match Claude Code's format
            if "metadata" not in body:
                body["metadata"] = {}
            if "user_id" not in body["metadata"]:
                # Load user_id from credentials or generate one
                _, user_id, account_uuid = load_oauth_credentials()
                user_id = user_id or "anonymous"
                account_uuid = account_uuid or "default"
                body["metadata"]["user_id"] = f"user_{user_id}_account_{account_uuid}_session_{_SESSION_ID}"
                print(f"[callbacks] Injected metadata.user_id: {body['metadata']['user_id']}", flush=True)

            print(f"[callbacks] Forwarding to Anthropic with {len(headers)} headers: {list(headers.keys())}", flush=True)
            api_url = api_base

        is_streaming = body.get("stream", False)
        logger.info(f"[callbacks] Completion request: model={body.get('model')}, stream={is_streaming}, route={'Z-AI' if is_zai_route else 'OAuth'}")

        if is_streaming:
            request_body_copy = body.copy()
            request_headers = headers.copy()
            request_url = api_url
            route_type = "Z-AI" if is_zai_route else "OAuth"

            async def stream_response():
                client = None
                response = None
                try:
                    client = httpx.AsyncClient(timeout=300.0)
                    req = client.build_request("POST", request_url, json=request_body_copy, headers=request_headers)
                    response = await client.send(req, stream=True)

                    if response.status_code != 200:
                        error_body = await response.aread()
                        logger.error(f"[callbacks] {route_type} streaming error: {response.status_code} {error_body.decode()}")
                        yield f"data: {json.dumps({'error': {'message': error_body.decode(), 'status': response.status_code}})}\n\n"
                        return

                    async for chunk in response.aiter_bytes():
                        yield chunk
                except Exception as e:
                    logger.error(f"[callbacks] {route_type} streaming error: {e}")
                    yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'streaming_error'}})}\n\n"
                finally:
                    if response:
                        await response.aclose()
                    if client:
                        await client.aclose()

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            route_type = "Z-AI" if is_zai_route else "OAuth"
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(api_url, json=body, headers=headers)
                if response.status_code != 200:
                    logger.error(f"[callbacks] {route_type} error: {response.status_code} {response.text}")
                    return JSONResponse(status_code=response.status_code, content={"error": {"message": response.text, "type": "api_error"}})
                return JSONResponse(content=response.json())

    except Exception as e:
        logger.error(f"[callbacks] OAuth completion error: {e}")
        return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": "internal_error"}})


# Register custom API endpoints
def register_custom_endpoints():
    """
    Register custom FastAPI endpoints on the LiteLLM proxy app.

    This is called when the module is loaded by LiteLLM.
    """
    try:
        from litellm.proxy.proxy_server import app
        from fastapi import Request
        from fastapi.responses import StreamingResponse, JSONResponse
        from starlette.middleware.base import BaseHTTPMiddleware
        import httpx
        import asyncio

        # =====================================================================
        # CRITICAL: Override /v1/messages route by removing LiteLLM's route
        # =====================================================================
        # LiteLLM's built-in Anthropic pass-through at /v1/messages BYPASSES
        # the callback system entirely. We remove their route and add our own.
        # =====================================================================

        # Find and remove LiteLLM's /v1/messages route
        routes_to_remove = []
        for i, route in enumerate(app.routes):
            if hasattr(route, 'path') and route.path == "/v1/messages":
                routes_to_remove.append(i)
                logger.info(f"[callbacks] Found existing /v1/messages route at index {i}")

        # Remove routes in reverse order to maintain indices
        for i in reversed(routes_to_remove):
            removed_route = app.routes.pop(i)
            logger.info(f"[callbacks] Removed existing /v1/messages route: {removed_route}")

        # Add our own /v1/messages route
        @app.post("/v1/messages")
        async def handle_v1_messages(request: Request):
            """
            Intercept /v1/messages for OAuth injection.

            This replaces LiteLLM's built-in pass-through which bypasses
            the callback system entirely.
            """
            logger.info("[callbacks] Handling /v1/messages request via custom route")
            body = await request.body()
            # Pass original headers for debugging and potential forwarding
            return await _handle_messages_request(body, dict(request.headers))

        logger.info("[callbacks] Added custom /v1/messages route")

        @app.post("/api/invalidate-credentials")
        async def handle_invalidate_credentials():
            """
            Endpoint to invalidate OAuth credential cache.

            Called by account-manager after credential sync to ensure
            proxy uses freshly synced credentials immediately.
            """
            result = invalidate_credential_cache()
            return result

        @app.post("/api/oauth-completion")
        async def handle_oauth_completion(request: Request):
            """
            Direct OAuth completion endpoint with agent-based routing.
            Uses shared handler for consistency with middleware.
            """
            body = await request.body()
            return await _handle_messages_request(body, dict(request.headers))

        logger.info("[callbacks] Registered custom endpoints: /api/invalidate-credentials, /api/oauth-completion")
    except ImportError as e:
        logger.warning(f"[callbacks] Could not register custom endpoints: {e}")
    except Exception as e:
        logger.warning(f"[callbacks] Error registering custom endpoints: {e}")


# Register endpoints when module is loaded
register_custom_endpoints()
