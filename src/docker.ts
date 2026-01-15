/**
 * Docker utilities for claude-proxy
 */
import { spawn, exec } from "node:child_process";
import { promisify } from "node:util";
import type { DockerOptions, ContainerInfo, HealthStatus } from "./types.js";

const execAsync = promisify(exec);

const DEFAULT_IMAGE = "claude-proxy:latest";
const DEFAULT_CONTAINER = "claude-proxy";

/**
 * Check if Docker is available
 */
export async function isDockerAvailable(): Promise<boolean> {
  try {
    await execAsync("docker --version");
    return true;
  } catch {
    return false;
  }
}

/**
 * Build Docker image from local Dockerfile
 */
export async function buildImage(
  contextPath: string,
  options: DockerOptions = {}
): Promise<void> {
  const imageName = options.imageName ?? DEFAULT_IMAGE;
  const dockerfilePath = `${contextPath}/Dockerfile`;

  return new Promise((resolve, reject) => {
    const args = ["build", "-t", imageName, "-f", dockerfilePath, contextPath];
    const proc = spawn("docker", args, { stdio: "inherit" });

    proc.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Docker build failed with code ${String(code)}`));
    });

    proc.on("error", reject);
  });
}

/**
 * Start a Docker container
 */
export async function startContainer(
  options: DockerOptions = {}
): Promise<string> {
  const imageName = options.imageName ?? DEFAULT_IMAGE;
  const containerName = options.containerName ?? DEFAULT_CONTAINER;
  const port = options.port ?? 4000;

  const args = [
    "run",
    "-d",
    "--name", containerName,
    "-p", `${String(port)}:4000`,
  ];

  // Add volume mounts
  if (options.volumes) {
    for (const [hostPath, containerPath] of Object.entries(options.volumes)) {
      args.push("-v", `${hostPath}:${containerPath}`);
    }
  }

  // Add environment variables
  if (options.env) {
    for (const [key, value] of Object.entries(options.env)) {
      args.push("-e", `${key}=${value}`);
    }
  }

  args.push(imageName);

  const { stdout } = await execAsync(`docker ${args.join(" ")}`);
  return stdout.trim(); // Returns container ID
}

/**
 * Stop a Docker container
 */
export async function stopContainer(
  containerNameOrId: string = DEFAULT_CONTAINER
): Promise<void> {
  try {
    await execAsync(`docker stop ${containerNameOrId}`);
    await execAsync(`docker rm ${containerNameOrId}`);
  } catch {
    // Container might not exist, ignore
  }
}

/**
 * Check if container is running
 */
export async function isContainerRunning(
  containerName: string = DEFAULT_CONTAINER
): Promise<boolean> {
  try {
    const { stdout } = await execAsync(
      `docker inspect -f '{{.State.Running}}' ${containerName}`
    );
    return stdout.trim() === "true";
  } catch {
    return false;
  }
}

/**
 * Get container health status
 */
export async function getContainerHealth(
  containerName: string = DEFAULT_CONTAINER
): Promise<HealthStatus> {
  try {
    const { stdout } = await execAsync(
      `docker inspect -f '{{.State.Health.Status}}' ${containerName}`
    );
    const status = stdout.trim();
    if (status === "healthy") return "healthy";
    if (status === "unhealthy") return "unhealthy";
    if (status === "starting") return "starting";
    return "unknown";
  } catch {
    return "stopped";
  }
}

/**
 * Get container info
 */
export async function getContainerInfo(
  containerName: string = DEFAULT_CONTAINER
): Promise<ContainerInfo | null> {
  try {
    const { stdout } = await execAsync(
      `docker inspect ${containerName} --format '{{json .}}'`
    );
    const info = JSON.parse(stdout) as {
      Id: string;
      Name: string;
      State: { Status: string };
      NetworkSettings: { Ports: Record<string, unknown> | null };
    };
    return {
      id: info.Id.slice(0, 12),
      name: info.Name.replace(/^\//, ""),
      status: info.State.Status,
      ports: Object.keys(info.NetworkSettings.Ports ?? {}),
      health: await getContainerHealth(containerName),
    };
  } catch {
    return null;
  }
}

/**
 * Stream container logs
 */
export function streamContainerLogs(
  containerName: string = DEFAULT_CONTAINER,
  onLog: (line: string) => void
): { stop: () => void } {
  const proc = spawn("docker", ["logs", "-f", containerName], {
    stdio: ["ignore", "pipe", "pipe"],
  });

  proc.stdout?.on("data", (data: Buffer) => {
    for (const line of data.toString().split("\n").filter(Boolean)) {
      onLog(line);
    }
  });

  proc.stderr?.on("data", (data: Buffer) => {
    for (const line of data.toString().split("\n").filter(Boolean)) {
      onLog(line);
    }
  });

  return {
    stop: () => proc.kill(),
  };
}
