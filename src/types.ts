/**
 * claude-proxy TypeScript types
 */

/** Execution mode for the proxy */
export type ExecutionMode = "docker" | "local";

/** Health status of the proxy */
export type HealthStatus = "healthy" | "unhealthy" | "starting" | "stopped" | "unknown";

/** Configuration for claude-proxy */
export interface ClaudeProxyConfig {
  version: number;
  routing: {
    agent_routing: boolean;
    model_routing: boolean;
  };
  fallback: {
    model: string;
    provider: string;
  };
  logging: {
    level: "debug" | "info" | "warning" | "error";
    format: "json" | "text";
  };
}

/** Validation result for config */
export interface ConfigValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/** Options for running the proxy */
export interface RunnerOptions {
  mode?: ExecutionMode;
  port?: number;
  host?: string;
  configPath?: string;
  debug?: boolean;
}

/** Options for Docker operations */
export interface DockerOptions {
  imageName?: string;
  containerName?: string;
  port?: number;
  volumes?: Record<string, string>;
  env?: Record<string, string>;
}

/** Container information */
export interface ContainerInfo {
  id: string;
  name: string;
  status: string;
  ports: string[];
  health: HealthStatus;
}
