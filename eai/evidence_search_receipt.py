"""P20 independently reconstruct exact-term local evidence from original bytes."""
from collections import Counter
import re

from .local_evidence_search import (
    EvidenceSearchGoal, VERSION, SCOPE, source_snapshot, text_lines
)

WORD_PATTERN = re.compile(r"[^\W_]+(?:[_-][^\W_]+)*", re.UNICODE)


def verify_search_receipt(goal: EvidenceSearchGoal, report: object) -> tuple[list[str], dict]:
    if type(goal) is not EvidenceSearchGoal or type(report) is not dict:
        raise ValueError("EAI evidence receipt invalid")
    sources = []
    all_matches = []
    for file_index, path in enumerate(goal.sources):
        binary, sha = source_snapshot(path)
        lines = text_lines(binary)
        sources.append({"filename": path.name, "sha256": sha,
                        "lines": len(lines)})
        for line_no, line in enumerate(lines, 1):
            # Separate counter-oriented scoring pass, not calling the primary
            # solver's _score or tokenize method.
            words = [match.group().casefold() for match in WORD_PATTERN.finditer(line)]
            counters = Counter(words)
            if all(counters[token] > 0 for token in goal.terms):
                repeats = min(1000, sum(counters[token] for token in goal.terms))
                bonus = 0
                if len(goal.terms) > 1:
                    for i in range(0, len(words) - len(goal.terms) + 1):
                        if tuple(words[i:i + len(goal.terms)]) == goal.terms:
                            bonus = 5
                            break
                all_matches.append({
                    "file_index": file_index, "filename": path.name,
                    "line": line_no, "score": repeats + bonus,
                    "excerpt": line[:160] if goal.include_snippets else None
                })
    all_matches.sort(key=lambda item: (
        -item["score"], item["file_index"], item["line"]))
    expected_matches = [
        {key: item[key] for key in ("filename", "line", "score", "excerpt")}
        for item in all_matches[:goal.max_results]
    ]
    for path, entry in zip(goal.sources, sources):
        if source_snapshot(path)[1] != entry["sha256"]:
            raise ValueError("evidence changed during receipt verification")
    status = "AGREE" if all_matches else "UNAVAILABLE"
    expected = {
        "version": VERSION, "kind": "local_evidence_search",
        "goal": goal.goal, "status": status, "terms": list(goal.terms),
        "max_results": goal.max_results, "include_snippets": goal.include_snippets,
        "sources": sources, "matching_lines": len(all_matches),
        "matches": expected_matches, "scope": SCOPE
    }
    if expected != report:
        raise ValueError("EAI evidence receipt failed: forged/inconsistent result")
    diagnosis = ({
        "type": "NO_EXACT_EVIDENCE", "action_required": True,
        "hint": "선택한 파일에 모든 단어가 함께 있는 줄이 없습니다. 범위를 재검토하세요."
    } if not all_matches else {"type": "NONE", "action_required": False})
    return ["original_sha256", "selected_source_list", "exact_term_coverage",
            "independent_rank", "privacy_consent", "status"], diagnosis
