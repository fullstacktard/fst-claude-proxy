/**
 * claude-proxy - Main exports
 */

// Types
export type {
  ExecutionMode,
  HealthStatus,
  ClaudeProxyConfig,
  ConfigValidationResult,
  RunnerOptions,
  DockerOptions,
  ContainerInfo,
} from "./types.js";

// Config
export {
  loadClaudeProxyConfig,
  validateClaudeProxyConfig,
  DEFAULT_CONFIG,
  CLAUDE_WORKFLOW_DIR,
  CLAUDE_PROXY_CONFIG_PATH,
  isAgentRoutingEnabled,
  isModelRoutingEnabled,
  getRoutingMode,
  getFallbackConfig,
} from "./config-loader.js";

// Docker utilities
export * as docker from "./docker.js";

// Runner
export { ClaudeProxyRunner } from "./runner.js";
