"""Build an explicitly requested, temporary practice library using real contracts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec
from .offline_journey import preview_offline_journey


class PracticeWorkspace:
    def __init__(self):
        self.temp = TemporaryDirectory(prefix="eai-practice-")
        try:
            root = Path(self.temp.name)
            self.library = root / "AXNODE"
            self.problem = root / "연습 목표.json"
            self.plan = root / "연습 계획.json"
            self.receipt = root / "검증 영수증.json"
            problem = {"version": 1, "id": "practice.workspace", "domain": "practice",
                       "goal": "두 로컬 후보의 단계와 근거를 비교합니다.", "risk": "LOW",
                       "state_refs": [], "assumptions": [], "hard_constraints": [],
                       "objectives": ["검토할 후보 찾기"], "oracle": "owner_review_required",
                       "permissions": ["pure"], "budget": {"max_steps": 8, "max_seconds": 60}}
            self.problem.write_text(json.dumps(problem, ensure_ascii=False), encoding="utf-8")
            with AXNodeStore(self.library) as store:
                parents = []
                for label, count in (("baseline", 1), ("review", 2), ("revision", 2)):
                    node = {"schema": "eai.axnode.v1", "id": "practice." + label,
                            "version": 1, "kind": "strategy", "status": "CANDIDATE",
                            "signature": {"inputs": {"source": "text"}, "output": "text"},
                            "pre": ["practice"], "post": ["owner_review"],
                            "steps": [{"skill": "synthetic.noop.v1"} for _ in range(count)],
                            "capabilities": ["pure"], "parent_hashes": parents if label == "revision" else [],
                            "tests": {"unit": [], "heldout": [], "negative": []}, "evidence": [],
                            "provenance": {"author": "eai", "source": "bundled_example"},
                            "budget": {"max_steps": count, "max_seconds": 1}}
                    parents = [store.import_node(json.dumps(node))]
            plan = {"version": 1, "problem_sha256": ProblemSpec.validate(problem).digest(),
                    "steps": [{"id": "inspect", "operator": "synthetic.noop.v1", "requires": [],
                               "capability": "pure"},
                              {"id": "review", "operator": "synthetic.noop.v1", "requires": ["inspect"],
                               "capability": "pure"}], "budget": {"max_steps": 2, "max_seconds": 5}}
            self.plan.write_text(json.dumps(plan), encoding="utf-8")
            report = preview_offline_journey(self.problem, self.library)
            self.receipt.write_text(json.dumps(report), encoding="utf-8")
        except BaseException:
            self.close()
            raise

    def close(self):
        self.temp.cleanup()
