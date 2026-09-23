# InsightFlow

InsightFlow is a controlled business analytics workbench built on the agent runtime from DeerFlow v2.1.0-rc0. It keeps the upstream MIT license and copyright notices; see [LICENSE](LICENSE) for the terms and [DeerFlow](https://github.com/bytedance/deer-flow) for the upstream project.

## What it provides

- Governed analytics for registered data sources, metrics, reports, and audit history.
- Thread-based analysis with streamed responses, artifacts, ordinary subagent tasks, and scheduled runs.
- A small web research path using DuckDuckGo search and Jina fetch.
- Operator-configured MCP servers and skills, with SkillScan checks on skill installation.
- Local and AIO sandbox modes for agent file and command tools.

The web workbench includes analysis, chats, data sources, metrics, reports, history, and scheduled tasks. It does not include the removed IM bridges, custom-agent editor, project/document/trash pages, or interactive browser control.

## Quick start

Requirements: Docker Compose, Python 3.12+, Node.js 22+, uv, and pnpm 10.26.2+.

1. Create local configuration and install dependencies:

   ~~~sh
   make config
   make install
   ~~~

2. Edit the gitignored config.yaml and set at least one model in models. Keep provider keys in environment variables, for example OPENAI_API_KEY or DEEPSEEK_API_KEY.
3. Start the development stack:

   ~~~sh
   make dev
   ~~~

Open http://localhost:2026. The published Nginx port binds to loopback by default. For the optimized local stack use make start; for the production Docker stack use make up. Run make stop or make down to stop the corresponding stack.

Never commit config.yaml, extensions_config.json, .env, or provider credentials. See [configuration](backend/docs/CONFIGURATION.md) and [deployment](Install.md) for setup details.

## Analytics and agent boundaries

Analytics queries pass through the governed query service: datasource credentials stay in server-side secret references, query plans are authorized before execution, and audit history is retained. Agent tools cannot bypass that service to query a registered datasource.

The lead agent can delegate ordinary tasks to built-in subagents. Scheduled runs use the lead agent and the normal Gateway run lifecycle. Local sandbox commands run with the Gateway host's privileges; AIO uses a separate sandbox service. An external AIO provisioner is only a configured client endpoint: this repository does not ship or start that service.

MCP servers and skills are operator-managed. Treat MCP servers, extensions, model providers, and sandbox endpoints as trusted code or services. Do not expose the Gateway directly to untrusted networks.

## Development

~~~sh
# Full application requirements
make check

# Backend
cd backend
make test
make lint

# Frontend
cd frontend
pnpm check
pnpm test
pnpm test:e2e
~~~

The backend default suite is offline; live provider tests are opt-in. See [backend development notes](backend/AGENTS.md), [frontend development notes](frontend/AGENTS.md), and [acceptance scenarios](docs/acceptance/acceptance-scenarios.md).

## License and attribution

This repository is derived from DeerFlow v2.1.0-rc0 and retains its MIT license and copyright notices. InsightFlow-specific changes are maintained in this repository. See [LICENSE](LICENSE).
