"""Example helper script for a skill.

Claude runs it as:  python3 scripts/example.py <name>
Keep scripts small, deterministic and dependency-free where possible.
"""

import sys


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "world"
    print(f"Hello, {name}!")


if __name__ == "__main__":
    main()
