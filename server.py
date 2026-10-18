"""DiceFrame MCP Bridge.

Exposes DiceFrame's bot-facing HTTP API as MCP tools, so an AI assistant
(Kimi custom plugin / Claude / etc.) can act as a player: submit actions,
read narration, ask the GM questions, check character sheets.

Config via environment variables:
  DICEFRAME_BASE_URL   e.g. https://diceframe-latest.onrender.com
  DICEFRAME_BOT_TOKEN  Bot API token from DiceFrame 设置 -> Bot API
  DICEFRAME_ACTOR      default player user_id the bot speaks as
  PORT                 listen port (default 8000)

Endpoints:
  /mcp      MCP streamable-http endpoint (what Claude/Kimi connect to)
  /healthz  plain-text liveness probe (ok)
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

BASE_URL = os.environ.get("DICEFRAME_BASE_URL", "").strip().rstrip("/")
BOT_TOKEN = os.environ.get("DICEFRAME_BOT_TOKEN", "").strip()
DEFAULT_ACTOR = os.environ.get("DICEFRAME_ACTOR", "").strip()
PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP("diceframe", host="0.0.0.0", port=PORT)


@mcp.custom_route("/healthz", methods=["GET"])
async def _healthz(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _call(method: str, path: str, body: dict | None = None, actor: str | None = None) -> Any:
    if not BASE_URL:
        return "ERROR: DICEFRAME_BASE_URL is not set."
    if not BOT_TOKEN:
        return "ERROR: DICEFRAME_BOT_TOKEN is not set."
    url = BASE_URL + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Bot-Token", BOT_TOKEN)
    who = DEFAULT_ACTOR if actor is None else actor
    if who:
        req.add_header("X-Bot-Actor", who)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        return f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001
        return f"REQUEST FAILED: {exc}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:2000]


def _clip(text: Any, limit: int = 6000) -> str:
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "\n...(截断)"


def _fingerprint(s: str) -> str:
    if not s:
        return "(空)"
    return f"长度{len(s)} 开头:{s[:4]!r} 结尾:{s[-4:]!r}"


@mcp.tool()
def debug_env() -> str:
    """诊断用：报告桥的环境变量是否填对（只看形状，不泄露完整密钥）。"""
    return "\n".join([
        f"DICEFRAME_BASE_URL = {_fingerprint(BASE_URL)}",
        f"DICEFRAME_BOT_TOKEN = {_fingerprint(BOT_TOKEN)}",
        f"DICEFRAME_ACTOR = {_fingerprint(DEFAULT_ACTOR)}",
        "提示：BASE_URL 应以 https:// 开头；BOT_TOKEN 若显示为 'DICF...' 开头，说明 key/value 填反了。",
    ])


@mcp.tool()
def ping() -> str:
    """Check the bridge can reach the DiceFrame server and the bot token works."""
    result = _call("GET", "/api/bot/ping")
    return _clip(result)


@mcp.tool()
def list_games() -> str:
    """List all games (save slots) on this DiceFrame server."""
    result = _call("GET", "/api/games")
    return _clip(result)


@mcp.tool()
def get_game(game_key: str) -> str:
    """Get full detail of one game: state, players, round, recent narration."""
    result = _call("GET", f"/api/games/{quote(game_key, safe='')}")
    return _clip(result)


@mcp.tool()
def get_characters(game_key: str) -> str:
    """Get character sheets of all players in a game (HP, sanity, skills...)."""
    result = _call("GET", f"/api/games/{quote(game_key, safe='')}/characters")
    return _clip(result)


@mcp.tool()
def act(game_key: str, action_text: str, confirm: bool = False, actor: str = "") -> str:
    """Submit a player action. THE main tool: describe what your character does
    in natural language; the engine decides dice and rules, then returns the GM
    narration plus any check results.

    Args:
        game_key: game identifier from list_games.
        action_text: what your character does / says.
        confirm: set True only when the engine asks you to confirm a roll.
        actor: your player user_id; leave empty to use the bridge default.
    """
    body: dict[str, Any] = {"text": action_text, "confirm": bool(confirm)}
    if confirm:
        body["server_roll"] = True
    result = _call("POST", f"/api/games/{quote(game_key, safe='')}/action", body=body,
                   actor=actor or None)
    if not isinstance(result, dict):
        return _clip(result)
    if result.get("ok") is False:
        return "ENGINE ERROR: " + _clip(result.get("error") or result)
    narration = result.get("narration") or ""
    checks_out = result.get("check_results") or []
    parts = ["【剧情】", narration] if narration else []
    if checks_out:
        parts.append("【判定结果】")
        parts.append(json.dumps(checks_out, ensure_ascii=False))
    if result.get("recap"):
        parts.append("【回顾】")
        parts.append(str(result["recap"]))
    if not parts:
        parts.append(_clip(result))
    return "\n".join(parts)


@mcp.tool()
def ask_kp(game_key: str, question: str, actor: str = "") -> str:
    """Ask the GM (KP) a read-only out-of-game question, e.g. rules checks."""
    result = _call(
        "POST",
        f"/api/games/{quote(game_key, safe='')}/kp-question",
        body={"question": question, "visibility": "party"},
        actor=actor or None,
    )
    return _clip(result)


@mcp.tool()
def private_log(game_key: str, actor: str = "") -> str:
    """Read a character's private log (clues only that player received)."""
    result = _call("GET", f"/api/games/{quote(game_key, safe='')}/private-log",
                   actor=actor or None)
    return _clip(result)


@mcp.tool()
def available_actions(game_key: str) -> str:
    """List currently available mechanical actions in this game."""
    result = _call("GET", f"/api/games/{quote(game_key, safe='')}/available-actions")
    return _clip(result)


if __name__ == "__main__":
    print(f"[diceframe-mcp-bridge] MCP at /mcp, healthz at /healthz, "
          f"port {PORT}, upstream={BASE_URL or '(unset)'}")
    mcp.run(transport="streamable-http")
