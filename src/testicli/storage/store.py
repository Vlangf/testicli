"""YAML-based storage for .testicli/ directory."""


from pathlib import Path

import yaml
from pydantic import BaseModel

from testicli.config import get_agent_dir
from testicli.models import ProjectConfig, TestFailure, TestPlan, TestRule


def _dump_yaml(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_yaml(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


class Store:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.agent_dir = get_agent_dir(project_root)

    @property
    def config_path(self) -> Path:
        return self.agent_dir / "config.yaml"

    @property
    def rules_path(self) -> Path:
        return self.agent_dir / "rules.yaml"

    @property
    def plans_dir(self) -> Path:
        return self.agent_dir / "plans"

    @property
    def failures_dir(self) -> Path:
        return self.agent_dir / "failures"

    # --- ProjectConfig ---

    def save_config(self, config: ProjectConfig) -> None:
        _dump_yaml(self.config_path, config.model_dump(mode="json"))

    def load_config(self) -> ProjectConfig | None:
        data = _load_yaml(self.config_path)
        if data is None:
            return None
        return ProjectConfig.model_validate(data)

    # --- Rules ---

    def save_rules(self, rules: list[TestRule]) -> None:
        _dump_yaml(self.rules_path, [r.model_dump(mode="json") for r in rules])

    def load_rules(self) -> list[TestRule]:
        data = _load_yaml(self.rules_path)
        if not data or not isinstance(data, list):
            return []
        return [TestRule.model_validate(r) for r in data]

    # --- Plans ---

    def _plan_filename(self, plan: TestPlan) -> str:
        lang_part = f"_{plan.language}" if plan.language else ""
        return f"plan_{plan.created_at:%Y%m%d_%H%M%S}_{plan.test_type.value}{lang_part}.yaml"

    def save_plan(self, plan: TestPlan) -> None:
        path = self.plans_dir / self._plan_filename(plan)
        _dump_yaml(path, plan.model_dump(mode="json"))

    def load_plans(self) -> list[TestPlan]:
        plans: list[TestPlan] = []
        if not self.plans_dir.exists():
            return plans
        for path in sorted(self.plans_dir.glob("plan_*.yaml")):
            data = _load_yaml(path)
            if data:
                plans.append(TestPlan.model_validate(data))
        return plans

    def load_latest_plan(self) -> TestPlan | None:
        plans = self.load_plans()
        return plans[-1] if plans else None

    def update_plan(self, plan: TestPlan) -> None:
        """Overwrite the plan file matching this plan's timestamp and type."""
        path = self.plans_dir / self._plan_filename(plan)
        _dump_yaml(path, plan.model_dump(mode="json"))

    # --- Failures ---

    def save_failure(self, failure: TestFailure) -> None:
        filename = f"fail_{failure.timestamp:%Y%m%d_%H%M%S}_{failure.test_name}.yaml"
        # Sanitize filename
        filename = filename.replace("/", "_").replace(" ", "_")
        path = self.failures_dir / filename
        _dump_yaml(path, failure.model_dump(mode="json"))

    def load_failures(self) -> list[TestFailure]:
        failures: list[TestFailure] = []
        if not self.failures_dir.exists():
            return failures
        for path in sorted(self.failures_dir.glob("fail_*.yaml")):
            data = _load_yaml(path)
            if data:
                failures.append(TestFailure.model_validate(data))
        return failures
