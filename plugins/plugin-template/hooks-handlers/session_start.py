"""SessionStart hook handler.

Claude Code sends the hook event as JSON on stdin; write a JSON result to stdout.
An empty object means "no changes". Exit quickly: hooks run on every session start.
"""

import json
import sys


def main() -> None:
    event = json.load(sys.stdin)  # e.g. event["session_id"], event["cwd"]
    _ = event
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
