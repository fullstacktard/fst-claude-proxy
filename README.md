# claude-proxy

LiteLLM proxy with per-agent model routing and OAuth token injection for Claude Code.

## Features

- **Agent Routing**: Automatically route requests to different Claude models based on agent fingerprints
- **Model Routing**: Route based on model names in API requests
- **OAuth Injection**: Inject Claude OAuth tokens for seamless authentication
- **Docker Support**: Run as a container with health checks
- **TypeScript SDK**: Full TypeScript wrapper with types

## Installation

### npm (TypeScript/Node.js)

```bash
npm install claude-proxy

# Start with Docker (default)
npx claude-proxy start

# Start with local Python
npx claude-proxy start --local
```

### Docker (Build Locally)

The Docker image must be built locally from the python directory:

```bash
# After npm install, build the Docker image
cd node_modules/claude-proxy/python
docker build -t claude-proxy .

# Run with your API key
docker run -p 4000:4000 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY claude-proxy
```

### Python (Local Development)

The Python server is bundled with the npm package. For direct Python usage:

```bash
# Install from local path after npm install
cd node_modules/claude-proxy/python
pip install -e .

# Start the server
claude-proxy start --port 4000
```

## CLI Commands

### Node.js CLI (via npx)

```bash
npx claude-proxy start [options]    # Start the proxy server
npx claude-proxy stop               # Stop the proxy server (Docker only)
npx claude-proxy status             # Show proxy status (Docker only)
npx claude-proxy config             # Show current configuration
npx claude-proxy logs [-f]          # View/stream proxy logs (Docker only)
```

### Python CLI (if installed separately)

```bash
claude-proxy start [options]        # Start the proxy server
claude-proxy generate-hashes <dir>  # Generate agent fingerprint hashes
claude-proxy config                 # Show current configuration
```

### Start Options

| Option | Default | Description |
|--------|---------|-------------|
| `--port, -p` | 4000 | Port to listen on |
| `--host` | 0.0.0.0 | Host to bind to |
| `--local` | false | Use local Python instead of Docker (Node.js CLI only) |
| `--config, -c` | - | Path to config file |
| `--debug` | false | Enable debug logging |

## Configuration

Configuration is stored at `~/.claude-workflow/claude-proxy-config.yaml` by default.

You can customize the config directory by setting the `CLAUDE_PROXY_CONFIG_DIR` environment variable:

```bash
export CLAUDE_PROXY_CONFIG_DIR=~/.my-custom-dir
# Config will be loaded from ~/.my-custom-dir/claude-proxy-config.yaml
```

Example configuration:

```yaml
version: 1
routing:
  agent_routing: true   # Route by agent fingerprint
  model_routing: false  # Route by model name
fallback:
  model: claude-sonnet-4-20250514
  provider: anthropic
logging:
  level: info
  format: json
```

> **Note**: `agent_routing` and `model_routing` are mutually exclusive. Only one can be enabled at a time.

## TypeScript API

```typescript
import { ClaudeProxyRunner, loadClaudeProxyConfig, docker } from 'claude-proxy';

// Load configuration
const config = loadClaudeProxyConfig();

// Create and start runner
const runner = new ClaudeProxyRunner({
  mode: 'docker',  // or 'local'
  port: 4000,
  debug: true,
});

await runner.start();

// Check health
const health = await runner.getHealth();
console.log('Proxy health:', health);

// Stop when done
await runner.stop();
```

## Docker Utilities

Docker utilities are exported from the main package:

```typescript
import { docker } from 'claude-proxy';

// Check if Docker is available
const available = await docker.isDockerAvailable();

// Start container (image must be built locally first)
const containerId = await docker.startContainer({
  port: 4000,
  volumes: { [`${process.env.HOME}/.claude-workflow`]: '/root/.claude-workflow:ro' },
});

// Get container info
const info = await docker.getContainerInfo();

// Stream logs
const { stop } = docker.streamContainerLogs('claude-proxy', console.log);
```

## Agent Routing

The proxy identifies agents by computing a hash of their system prompt. Generate hashes using the Python CLI:

```bash
# After installing the Python package
claude-proxy generate-hashes ./path/to/agents/

# Or using Python directly
python -m claude_proxy.generate_hashes --agents-dir ./path/to/agents/
```

This creates `agent_hashes.json` mapping agent fingerprints to model preferences.

## Exports

The package exports the following:

```typescript
// Types
export type { ExecutionMode, HealthStatus, ClaudeProxyConfig, ConfigValidationResult, RunnerOptions, DockerOptions, ContainerInfo } from 'claude-proxy';

// Config utilities
export { loadClaudeProxyConfig, validateClaudeProxyConfig, DEFAULT_CONFIG, CLAUDE_WORKFLOW_DIR, CONFIG_PATH, isAgentRoutingEnabled, isModelRoutingEnabled, getRoutingMode, getFallbackConfig } from 'claude-proxy';

// Docker utilities
export { docker } from 'claude-proxy';

// Runner
export { ClaudeProxyRunner } from 'claude-proxy';
```

## License

MIT
