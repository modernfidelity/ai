"""Phase 0 smoke test: one model call, print the reply, usage and cost.

    python smoke_test.py                      # Claude Code login (default), haiku
    python smoke_test.py --model sonnet
    python smoke_test.py --backend api        # needs ANTHROPIC_API_KEY
"""

import argparse
import sys

PROMPT = "Reply with exactly: eval smoke test OK"


def run_cli(model: str) -> None:
    from common.claude_cli import ClaudeCLIError, complete

    try:
        c = complete(PROMPT, model=model)
    except ClaudeCLIError as e:
        sys.exit(str(e))
    print(f"backend:     claude -p (Claude Code login)")
    print(f"model:       {c.model}")
    print(f"stop_reason: {c.stop_reason}")
    print(f"reply:       {c.text}")
    print(f"tokens:      in={c.input_tokens} out={c.output_tokens}")
    print(f"cost (list): ${c.cost_usd:.6f}  ({c.duration_ms} ms)")


def run_api(model: str) -> None:
    import anthropic

    from common.client import cost_usd, get_client

    try:
        client = get_client()
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": PROMPT}],
        )
    except TypeError as e:
        if "authentication method" not in str(e):
            raise
        sys.exit("No credentials found: export ANTHROPIC_API_KEY (or run `ant auth login`).")
    except anthropic.AuthenticationError:
        sys.exit("Auth failed: set ANTHROPIC_API_KEY (or run `ant auth login`).")
    except anthropic.APIStatusError as e:
        sys.exit(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError as e:
        sys.exit(f"Connection error: {e}")

    if response.stop_reason == "refusal":
        sys.exit(f"Refused: {response.stop_details}")

    text = "".join(b.text for b in response.content if b.type == "text")
    print(f"backend:     Anthropic API")
    print(f"model:       {response.model}")
    print(f"stop_reason: {response.stop_reason}")
    print(f"reply:       {text.strip()}")
    print(f"tokens:      in={response.usage.input_tokens} out={response.usage.output_tokens}")
    print(f"cost:        ${cost_usd(model, response.usage):.6f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["cli", "api"], default="cli")
    p.add_argument("--model", help="cli: haiku|sonnet|opus or full id; api: full id")
    args = p.parse_args()
    if args.backend == "cli":
        run_cli(args.model or "haiku")
    else:
        from common.client import DEFAULT_MODEL

        run_api(args.model or DEFAULT_MODEL)
