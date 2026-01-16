/**
 * ClaudeProxyRunner - Abstracts Docker vs local Python execution
 */
import { spawn, type ChildProcess } from "node:child_process";
import type { ExecutionMode, RunnerOptions, HealthStatus } from "./types.js";
import * as docker from "./docker.js";

export class ClaudeProxyRunner {
  private mode: ExecutionMode;
  private port: number;
  private host: string;
  private configPath?: string;
  private debug: boolean;
  private process: ChildProcess | null = null;

  constructor(options: RunnerOptions = {}) {
    this.mode = options.mode ?? "docker";
    this.port = options.port ?? 4000;
    this.host = options.host ?? "0.0.0.0";
    this.configPath = options.configPath;
    this.debug = options.debug ?? false;
  }

  /**
   * Start the proxy
   */
  async start(): Promise<void> {
    if (await this.isRunning()) {
      throw new Error("Proxy is already running");
    }

    await (this.mode === "docker" ? this.startDocker() : this.startLocal());
  }

  /**
   * Stop the proxy
   */
  async stop(): Promise<void> {
    if (this.mode === "docker") {
      await docker.stopContainer();
      // Container stopped
    } else if (this.process) {
      this.process.kill("SIGTERM");
      this.process = null;
    }
  }

  /**
   * Check if proxy is running
   */
  async isRunning(): Promise<boolean> {
    return this.mode === "docker" ? docker.isContainerRunning() : this.process !== null && this.process.exitCode === null;
  }

  /**
   * Get health status
   */
  async getHealth(): Promise<HealthStatus> {
    if (this.mode === "docker") {
      return docker.getContainerHealth();
    } else {
      // For local mode, try to hit the health endpoint
      try {
        const response = await fetch(`http://${this.host}:${String(this.port)}/health`);
        return response.ok ? "healthy" : "unhealthy";
      } catch {
        return this.process ? "starting" : "stopped";
      }
    }
  }

  /**
   * Get current mode
   */
  getMode(): ExecutionMode {
    return this.mode;
  }

  private async startDocker(): Promise<void> {
    const available = await docker.isDockerAvailable();
    if (!available) {
      throw new Error("Docker is not available. Install Docker or use --local mode.");
    }

    // Use CLAUDE_PROXY_CONFIG_DIR if set, otherwise default to ~/.claude-workflow
    const configDir = process.env.CLAUDE_PROXY_CONFIG_DIR ?? `${process.env.HOME ?? ""}/.claude-workflow`;
    const volumes: Record<string, string> = {
      [configDir]: "/root/.claude-workflow:ro",
    };

    const env: Record<string, string> = {
      PROXY_PORT: String(this.port),
      PROXY_HOST: this.host,
    };

    if (this.configPath) {
      env.LITELLM_CONFIG = this.configPath;
    }

    if (this.debug) {
      env.DEBUG = "true";
    }

    await docker.startContainer({
      port: this.port,
      volumes,
      env,
    });
  }

  private startLocal(): Promise<void> {
    return new Promise((resolve, reject) => {
      const args = ["-m", "claude_proxy", "start", "--port", String(this.port), "--host", this.host];

      if (this.configPath) {
        args.push("--config", this.configPath);
      }

      if (this.debug) {
        args.push("--debug");
      }

      this.process = spawn("python", args, {
        stdio: "inherit",
        env: { ...process.env },
      });

      this.process.on("error", (err) => {
        console.error("Failed to start local Python process:", err.message);
        this.process = null;
        reject(err);
      });

      // Give it a moment to start before resolving
      setTimeout(() => {
        if (this.process && this.process.exitCode === null) {
          resolve();
        } else {
          reject(new Error("Process exited unexpectedly"));
        }
      }, 1000);
    });
  }
}
