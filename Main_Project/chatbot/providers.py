"""
Pluggable LLM backends.

The agent loop in `agent.py` is provider-agnostic: it holds the conversation in a
neutral format (see `Turn` below) and asks a provider to produce the next
assistant turn. Anything that can (a) follow a system prompt and (b) call tools
can back this app.

To add a provider, either register another OpenAI-compatible endpoint in
PROVIDERS (one line — most inference services speak this protocol), or subclass
LLMProvider for an API with its own shape. See CONTRIBUTING.md.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    """One assistant turn, normalized across providers."""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    # Provider-native content, replayed verbatim when the same provider
    # continues the conversation. Anthropic requires this: thinking blocks must
    # be passed back unchanged or the next request is rejected.
    raw: object | None = None
    raw_provider: str | None = None


class LLMProvider(ABC):
    """A chat backend that supports tool calling."""

    name: str = ""
    label: str = ""
    models: list[str] = []
    key_env: str = ""
    key_help: str = ""
    requires_key: bool = True

    def __init__(self, api_key: str = "", model: str = "", base_url: str = ""):
        self.api_key = api_key or os.environ.get(self.key_env, "")
        self.model = model or (self.models[0] if self.models else "")
        self.base_url = base_url

    @abstractmethod
    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        """Send the conversation and return the next assistant turn.

        `messages` is the neutral history built by `agent.py`:
          {"role": "user",         "content": str}
          {"role": "assistant",    "content": str, "tool_calls": [...], "raw": ..., "raw_provider": str}
          {"role": "tool_results", "results": [{"id", "name", "output"}]}

        `tools` is the neutral tool schema: {"name", "description", "input_schema"}.
        """
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    """Claude via the official Anthropic SDK."""

    name = "anthropic"
    label = "Anthropic (Claude)"
    models = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]
    key_env = "ANTHROPIC_API_KEY"
    key_help = "console.anthropic.com"

    MAX_TOKENS = 16000

    def __init__(self, *args, effort: str = "high", **kwargs):
        super().__init__(*args, **kwargs)
        self.effort = effort

    def _to_native(self, messages: list[dict]) -> list[dict]:
        native = []
        for msg in messages:
            if msg["role"] == "user":
                native.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                # Replay our own blocks verbatim — thinking blocks must survive.
                if msg.get("raw_provider") == self.name and msg.get("raw") is not None:
                    native.append({"role": "assistant", "content": msg["raw"]})
                    continue
                blocks = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": msg["content"]})
                for call in msg.get("tool_calls", []):
                    blocks.append({
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    })
                native.append({"role": "assistant", "content": blocks})
            elif msg["role"] == "tool_results":
                native.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r["id"],
                            "content": json.dumps(r["output"], default=str),
                        }
                        for r in msg["results"]
                    ],
                })
        return native

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            system=system,
            messages=self._to_native(messages),
            tools=[
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["input_schema"],
                }
                for t in tools
            ],
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
        )

        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
            for b in response.content
            if b.type == "tool_use"
        ]
        return Turn(
            text=text,
            tool_calls=calls,
            stop_reason=response.stop_reason or "end_turn",
            raw=response.content,
            raw_provider=self.name,
        )


class OpenAICompatProvider(LLMProvider):
    """Any endpoint that speaks the OpenAI chat-completions protocol.

    Covers OpenRouter, Groq, Together, Fireworks, DeepSeek, vLLM, llama.cpp and
    Ollama — which is most of the open-source serving ecosystem.
    """

    MAX_TOKENS = 4096

    def _to_native(self, system: str, messages: list[dict]) -> list[dict]:
        native = [{"role": "system", "content": system}]
        for msg in messages:
            if msg["role"] == "user":
                native.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                entry = {"role": "assistant", "content": msg.get("content") or None}
                if msg.get("tool_calls"):
                    entry["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments),
                            },
                        }
                        for c in msg["tool_calls"]
                    ]
                native.append(entry)
            elif msg["role"] == "tool_results":
                # One tool message per call, unlike Anthropic's single user turn.
                for r in msg["results"]:
                    native.append({
                        "role": "tool",
                        "tool_call_id": r["id"],
                        "content": json.dumps(r["output"], default=str),
                    })
        return native

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key or "not-needed", base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            messages=self._to_native(system, messages),
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ],
        )

        choice = response.choices[0]
        calls = []
        for tc in choice.message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                # Smaller open models occasionally emit malformed JSON; surface
                # it as a tool error rather than crashing the turn.
                args = {"__parse_error__": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return Turn(
            text=(choice.message.content or "").strip(),
            tool_calls=calls,
            stop_reason=choice.finish_reason or "end_turn",
        )


def _openai_compat(name, label, base_url, models, key_env, key_help, requires_key=True):
    """Build a provider class for an OpenAI-compatible endpoint."""
    return type(
        f"{name.title()}Provider",
        (OpenAICompatProvider,),
        {
            "name": name,
            "label": label,
            "models": models,
            "key_env": key_env,
            "key_help": key_help,
            "requires_key": requires_key,
            "__init__": lambda self, api_key="", model="", base_url=base_url, **kw:
                LLMProvider.__init__(self, api_key, model, base_url),
        },
    )


# Model IDs move fast in the open-source ecosystem — these are sensible defaults,
# and every provider accepts a custom model ID from the UI.
PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openrouter": _openai_compat(
        "openrouter", "OpenRouter (open models)",
        "https://openrouter.ai/api/v1",
        [
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
            "deepseek/deepseek-chat",
            "mistralai/mistral-large",
        ],
        "OPENROUTER_API_KEY", "openrouter.ai/keys",
    ),
    "groq": _openai_compat(
        "groq", "Groq (fast open models)",
        "https://api.groq.com/openai/v1",
        ["llama-3.3-70b-versatile", "qwen/qwen3-32b", "moonshotai/kimi-k2-instruct"],
        "GROQ_API_KEY", "console.groq.com/keys",
    ),
    "together": _openai_compat(
        "together", "Together AI (open models)",
        "https://api.together.xyz/v1",
        [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-V3",
        ],
        "TOGETHER_API_KEY", "api.together.ai/settings/api-keys",
    ),
    "ollama": _openai_compat(
        "ollama", "Ollama (local, no key)",
        "http://localhost:11434/v1",
        ["llama3.3", "qwen2.5", "mistral-nemo"],
        "", "ollama.com — run `ollama serve` first",
        requires_key=False,
    ),
}


def get_provider(name: str, **kwargs) -> LLMProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {name}. Options: {', '.join(PROVIDERS)}")
    return PROVIDERS[name](**kwargs)
