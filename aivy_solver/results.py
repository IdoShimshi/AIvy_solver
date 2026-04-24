import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AttemptRecord:
    attempt: int
    passed: bool
    ivy_output: str
    llm_solution: str
    reasoning: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProblemResult:
    problem_name: str
    model: str
    success: bool
    success_on_attempt: int | None
    total_attempts: int
    attempts: list[AttemptRecord] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RunResult:
    model: str
    problems: list[ProblemResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def success_rate(self) -> float:
        if not self.problems:
            return 0.0
        return sum(1 for p in self.problems if p.success) / len(self.problems)

    def save(self, results_dir: Path) -> Path:
        results_dir.mkdir(parents=True, exist_ok=True)
        safe_model = self.model.replace("/", "_").replace(":", "_")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = results_dir / f"{safe_model}_{ts}.json"
        path.write_text(json.dumps(asdict(self), indent=2))
        return path
