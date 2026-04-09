from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    benchmarks_dir: Path = field(default_factory=lambda: Path("benchmarks"))
    results_dir: Path = field(default_factory=lambda: Path("results"))
    model: str = "openrouter/google/gemini-2.5-flash-preview"
    max_attempts: int = 10
    temperature: float = 0.3
    ivy_check_timeout: int = 30
    ivy_check_command: str = "ivy_check"
