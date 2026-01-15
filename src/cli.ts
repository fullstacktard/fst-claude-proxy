#!/usr/bin/env node
/**
 * claude-proxy CLI
 */
import { Command } from "commander";
import { exec, type ExecException } from "node:child_process";
import { ClaudeProxyRunner } from "./runner.js";
import * as docker from "./docker.js";
import { loadClaudeProxyConfig } from "./config-loader.js";

const program = new Command();

program
  .name("claude-proxy")
  .description("LiteLLM proxy with per-agent model routing and OAuth injection for Claude")
  .version("0.1.0");

program
  .command("start")
  .description("Start the proxy server")
  .option("-p, --port <port>", "Port to listen on", "4000")
  .option("-h, --host <host>", "Host to bind to", "0.0.0.0")
  .option("--local", "Use local Python instead of Docker")
  .option("-c, --config <path>", "Path to configuration file")
  .option("--debug", "Enable debug logging")
  .action(async (options: { port: string; host: string; local?: boolean; config?: string; debug?: boolean }) => {
    const runner = new ClaudeProxyRunner({
      mode: options.local ? "local" : "docker",
      port: Number.parseInt(options.port, 10),
      host: options.host,
      configPath: options.config,
      debug: options.debug,
    });

    try {
      console.log(`Starting claude-proxy in ${runner.getMode()} mode...`);
      await runner.start();
      console.log(`Proxy started on port ${options.port}`);

      // Keep process alive and handle shutdown
      process.on("SIGINT", () => {
        console.log("\nStopping proxy...");
        void runner.stop().then(() => {
          process.exit(0);
        });
      });

      process.on("SIGTERM", () => {
        void runner.stop().then(() => {
          process.exit(0);
        });
      });
    } catch (error) {
      console.error("Failed to start proxy:", error instanceof Error ? error.message : String(error));
      process.exit(1);
    }
  });

program
  .command("stop")
  .description("Stop the proxy server")
  .action(async () => {
    try {
      await docker.stopContainer();
      console.log("Proxy stopped");
    } catch (error) {
      console.error("Failed to stop proxy:", error instanceof Error ? error.message : String(error));
      process.exit(1);
    }
  });

program
  .command("status")
  .description("Show proxy status")
  .action(async () => {
    const info = await docker.getContainerInfo();
    if (info) {
      console.log(`Status: ${info.status}`);
      console.log(`Health: ${info.health}`);
      console.log(`Container: ${info.name} (${info.id})`);
      console.log(`Ports: ${info.ports.join(", ")}`);
    } else {
      console.log("Status: stopped");
      console.log("No container running");
    }
  });

program
  .command("config")
  .description("Show current configuration")
  .action(() => {
    const config = loadClaudeProxyConfig({ silent: true });
    if (config) {
      console.log(JSON.stringify(config, null, 2));
    } else {
      console.log("No configuration found. Using defaults.");
    }
  });

program
  .command("logs")
  .description("Stream proxy logs")
  .option("-f, --follow", "Follow log output")
  .action((options: { follow?: boolean }) => {
    if (options.follow) {
      console.log("Streaming logs (Ctrl+C to stop)...\n");
      const { stop } = docker.streamContainerLogs("claude-proxy", (line) => {
        console.log(line);
      });

      process.on("SIGINT", () => {
        stop();
        process.exit(0);
      });
    } else {
      exec("docker logs claude-proxy --tail 100", (
        err: ExecException | null,
        stdout: string,
        stderr: string
      ) => {
        if (err) {
          console.error("Failed to get logs:", err.message);
          process.exit(1);
        }
        console.log(stdout);
        if (stderr) console.error(stderr);
      });
    }
  });

program.parse();
