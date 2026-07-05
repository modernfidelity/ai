import platform
import random
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("Local Tools")


@mcp.tool
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@mcp.tool
def list_directory(path: str = ".") -> list[str]:
    """List the names of files and folders inside a directory."""
    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        raise ValueError(f"{target} is not a directory")
    return sorted(p.name for p in target.iterdir())


@mcp.tool
def read_text_file(path: str, max_chars: int = 5000) -> str:
    """Read the contents of a text file, truncated to max_chars."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError(f"{target} is not a file")
    return target.read_text(errors="replace")[:max_chars]


@mcp.tool
def system_info() -> dict:
    """Return basic information about the local machine."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


@mcp.tool
def roll_dice(sides: int = 6, count: int = 1) -> list[int]:
    """Roll `count` dice each with `sides` faces and return the results."""
    return [random.randint(1, sides) for _ in range(count)]


if __name__ == "__main__":
    mcp.run()
