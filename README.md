# diceframe-mcp-bridge

MCP (streamable-http) bridge to a self-hosted [DiceFrame](https://github.com/diceframe/diceframe) server, using its official bot API (`X-Bot-Token`).

Lets an AI assistant (Kimi custom plugin, Claude Code, etc.) act as a TRPG player: submit actions, read narration, ask the GM, inspect sheets.

## Env vars

| Var | Meaning |
|---|---|
| `DICEFRAME_BASE_URL` | Your DiceFrame server, e.g. `https://diceframe-latest.onrender.com` |
| `DICEFRAME_BOT_TOKEN` | Bot API token from DiceFrame 设置 -> Bot API |
| `DICEFRAME_ACTOR` | Default player user_id the bot speaks as |
| `PORT` | Listen port, default 8000 |

Endpoint: `http://<host>:8000/mcp` (streamable HTTP).

## Deploy on Render (free)

1. New -> Web Service -> connect this repo.
2. Runtime: Docker. Instance: free (512 MB is enough).
3. Set the env vars above.
4. After deploy, add the MCP URL as a custom plugin in Kimi: `https://<your-service>.onrender.com/mcp`.
