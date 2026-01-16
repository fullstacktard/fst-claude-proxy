/**
 * claude-proxy configuration loader
 *
 * Loads and validates configuration from ~/.claude-workflow/claude-proxy-config.yaml
 * Enforces mutual exclusivity between agent_routing and model_routing modes.
 *
 * @example
 * const config = loadClaudeProxyConfig();
 * if (config) {
 *   console.log('Agent routing enabled:', config.routing.agent_routing);
 * }
 */
import { existsSync, readFileSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as yaml from "js-yaml";
/**
 * Global workflow directory path
 * Can be overridden via CLAUDE_PROXY_CONFIG_DIR environment variable for standalone usage
 */
export const CLAUDE_WORKFLOW_DIR = process.env.CLAUDE_PROXY_CONFIG_DIR ?? path.join(os.homedir(), ".claude-workflow");
/**
 * Path to claude-proxy configuration file
 */
export const CLAUDE_PROXY_CONFIG_PATH = path.join(CLAUDE_WORKFLOW_DIR, "claude-proxy-config.yaml");
/**
 * Default configuration values
 */
export const DEFAULT_CONFIG = {
    version: 1,
    routing: {
        agent_routing: true,
        model_routing: false,
    },
    fallback: {
        model: "claude-sonnet-4-20250514",
        provider: "anthropic",
    },
    logging: {
        level: "info",
        format: "json",
    },
};
/**
 * Validate claude-proxy configuration
 * Enforces mutual exclusivity of routing modes
 *
 * @param config - Configuration to validate
 * @returns Validation result with errors and warnings
 */
export function validateClaudeProxyConfig(config) {
    const errors = [];
    const warnings = [];
    // Check mutual exclusivity: agent_routing XOR model_routing
    if (config.routing.agent_routing && config.routing.model_routing) {
        errors.push("agent_routing and model_routing are mutually exclusive. Only one can be enabled at a time.");
    }
    // Warn if both are disabled
    if (!config.routing.agent_routing && !config.routing.model_routing) {
        warnings.push("Both routing modes are disabled. Requests will use fallback model directly.");
    }
    // Validate version
    if (config.version !== 1) {
        warnings.push(`Unknown config version: ${String(config.version)}. Expected version 1.`);
    }
    // Validate logging level
    const validLevels = ["debug", "info", "warning", "error"];
    if (!validLevels.includes(config.logging.level)) {
        errors.push(`Invalid logging level: ${config.logging.level}. Must be one of: ${validLevels.join(", ")}`);
    }
    // Validate logging format
    const validFormats = ["json", "text"];
    if (!validFormats.includes(config.logging.format)) {
        errors.push(`Invalid logging format: ${config.logging.format}. Must be one of: ${validFormats.join(", ")}`);
    }
    return {
        valid: errors.length === 0,
        errors,
        warnings,
    };
}
/**
 * Load and validate claude-proxy config from global folder
 *
 * @param options - Loading options
 * @param options.silent - Suppress warning messages
 * @returns Loaded configuration or null if not found/invalid
 */
export function loadClaudeProxyConfig(options = {}) {
    const { silent = false } = options;
    if (!existsSync(CLAUDE_PROXY_CONFIG_PATH)) {
        return null;
    }
    try {
        const content = readFileSync(CLAUDE_PROXY_CONFIG_PATH, "utf8");
        const rawConfig = yaml.load(content);
        // Merge with defaults to handle missing fields
        const config = {
            version: rawConfig.version ?? DEFAULT_CONFIG.version,
            routing: {
                agent_routing: rawConfig.routing?.agent_routing ??
                    DEFAULT_CONFIG.routing.agent_routing,
                model_routing: rawConfig.routing?.model_routing ??
                    DEFAULT_CONFIG.routing.model_routing,
            },
            fallback: {
                model: rawConfig.fallback?.model ??
                    DEFAULT_CONFIG.fallback.model,
                provider: rawConfig.fallback?.provider ??
                    DEFAULT_CONFIG.fallback.provider,
            },
            logging: {
                level: rawConfig.logging?.level ??
                    DEFAULT_CONFIG.logging.level,
                format: rawConfig.logging?.format ??
                    DEFAULT_CONFIG.logging.format,
            },
        };
        const validation = validateClaudeProxyConfig(config);
        if (!validation.valid && !silent) {
            console.warn("[claude-proxy] Config validation errors:", validation.errors.join(", "));
        }
        if (validation.warnings.length > 0 && !silent) {
            console.warn("[claude-proxy] Config warnings:", validation.warnings.join(", "));
        }
        return config;
    }
    catch (error) {
        if (!silent) {
            console.warn(`[claude-proxy] Failed to load config: ${error instanceof Error ? error.message : String(error)}`);
        }
        return null;
    }
}
/**
 * Check if agent routing is enabled
 * Convenience function for quick checks
 *
 * @returns true if agent routing is enabled, false otherwise
 */
export function isAgentRoutingEnabled() {
    const config = loadClaudeProxyConfig({ silent: true });
    return config?.routing.agent_routing ?? DEFAULT_CONFIG.routing.agent_routing;
}
/**
 * Check if model routing is enabled
 * Convenience function for quick checks
 *
 * @returns true if model routing is enabled, false otherwise
 */
export function isModelRoutingEnabled() {
    const config = loadClaudeProxyConfig({ silent: true });
    return config?.routing.model_routing ?? DEFAULT_CONFIG.routing.model_routing;
}
/**
 * Get the effective routing mode
 *
 * @returns "agent" | "model" | "passthrough"
 */
export function getRoutingMode() {
    const config = loadClaudeProxyConfig({ silent: true });
    if (config?.routing.agent_routing) {
        return "agent";
    }
    if (config?.routing.model_routing) {
        return "model";
    }
    return "passthrough";
}
/**
 * Get fallback configuration
 *
 * @returns Fallback configuration with defaults applied
 */
export function getFallbackConfig() {
    const config = loadClaudeProxyConfig({ silent: true });
    return config?.fallback ?? DEFAULT_CONFIG.fallback;
}
