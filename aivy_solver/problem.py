from dataclasses import dataclass
from pathlib import Path


@dataclass
class Problem:
    name: str
    ground_truth: str
    stripped: str

    @classmethod
    def load(cls, problem_dir: Path) -> "Problem":
        gt_path = problem_dir / "ground_truth.ivy"
        stripped_path = problem_dir / "stripped.ivy"
        return cls(
            name=problem_dir.name,
            ground_truth=gt_path.read_text(),
            stripped=stripped_path.read_text(),
        )

    @classmethod
    def load_all(cls, benchmarks_dir: Path) -> list["Problem"]:
        problems = []
        for d in sorted(benchmarks_dir.iterdir()):
            if d.is_dir() and (d / "stripped.ivy").exists():
                problems.append(cls.load(d))
        return problems
