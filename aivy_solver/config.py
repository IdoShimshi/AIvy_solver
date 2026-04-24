import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    benchmarks_dir: Path = field(default_factory=lambda: Path("benchmarks"))
    results_dir: Path = field(default_factory=lambda: Path("results"))
    model: str = "openrouter/google/gemini-2.5-flash-lite"
    max_attempts: int = 5
    temperature: float = 0.0
    reasoning_effort: str | None = "default"
    ivy_check_timeout: int = 30
    concurrency: int = 1
    ivy_check_command: str = field(
        default_factory=lambda: os.environ.get("IVY_CHECK_COMMAND", "ivy_check")
    )
