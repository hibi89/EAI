"""Pre-built, versioned, permission-scoped workflow templates (no new code generation)."""
from dataclasses import dataclass
from .tools import SearchHit, ToolRegistry


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    tool_id: str
    max_results: int
    needs_online_consent: bool = True


class WorkflowRegistry:
    def __init__(self):
        self._templates = {
            "research.web.v1": WorkflowTemplate(
                name="research.web.v1", tool_id="web.search.v1", max_results=5
            )
        }

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._templates))

    def execute(
        self, name: str, tools: ToolRegistry, query: str, *, allow_online: bool = False
    ) -> list[SearchHit]:
        template = self._templates[name]
        if template.needs_online_consent and not allow_online:
            raise PermissionError("online workflow requires explicit approval")
        search_tool = tools.get(template.tool_id)
        return search_tool.search(query, limit=template.max_results)
