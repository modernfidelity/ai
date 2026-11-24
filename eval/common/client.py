"""Shared Anthropic client + pricing helpers for the eval harnesses."""

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"

# USD per 1M tokens (input, output). Keep in sync with Anthropic's pricing page.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def get_client() -> anthropic.Anthropic:
    # Resolves ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / `ant auth login` profile.
    return anthropic.Anthropic()


def cost_usd(model: str, usage) -> float:
    """Approximate cost of one response from its usage block (ignores caching)."""
    in_rate, out_rate = PRICING[model]
    return (usage.input_tokens * in_rate + usage.output_tokens * out_rate) / 1_000_000
