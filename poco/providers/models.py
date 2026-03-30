from typing import List


PREDEFINED_MODELS = {
    "codex": [
        "gpt-5.2-codex",
        "gpt-5.2",
        "gpt-5.2-pro",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini",
        "gpt-5.1",
        "gpt-5.4",
        "gpt-5-codex",
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "codex-mini-latest",
    ],
    "claude": {
        "anthropic": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
        "deepseek": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "kimi": [
            "kimi-k2.5",
            "kimi-k2-0905-preview",
            "kimi-k2-0711-preview",
            "kimi-k2-turbo-preview",
            "kimi-k2-thinking",
            "kimi-k2-thinking-turbo",
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "moonshot-v1-8k-vision-preview",
            "moonshot-v1-32k-vision-preview",
            "moonshot-v1-128k-vision-preview",
        ],
        "minimax": [
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
    },
}


def model_choices(provider_name: str, backend_name: str | None = None) -> List[str]:
    provider = provider_name.strip().lower()
    payload = PREDEFINED_MODELS.get(provider, [])
    if isinstance(payload, dict):
        backend = (backend_name or "").strip().lower()
        return list(payload.get(backend, []))
    return list(payload)
