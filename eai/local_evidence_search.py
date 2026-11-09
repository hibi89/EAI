"""P20 CPU-owned bounded evidence search over explicitly chosen local text files.

No network, file modification, automatic directory traversal, or LLM rendering.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

VERSION = "eai.goal.local_evidence_search.v1"
SCOPE = ("명시적으로 선택한 로컬 텍스트 파일에서 정확한 단어의 공통 등장 줄을 검색합니다. "
         "언어 모델의 답변·사실 검증·의미 검색은 아닙니다. 문서 신뢰성은 보장하지 않습니다. "
         "발췌는 명시적 동의 옵션인 include_snippets=true 에서만 로컬 출력하며, "
         "원본 수정·자동 디렉터리 순회·원격 전송은 수행하지 않습니다.")
MAX_FILE_BYTES = 256 * 1024
MAX_LINES = 5000
MAX_LINE_LENGTH = 2000
TOKEN_RE = re.compile(r"[^\W_]+(?:[_-][^\W_]+)*", re.UNICODE)
TERM_RE = re.compile(r"[^\W_]+(?:[_-][^\W_]+)*\Z", re.UNICODE)


@dataclass(frozen=True)
class EvidenceSearchGoal:
    goal: str
    root: Path
    sources: tuple[Path, ...]
    terms: tuple[str, ...]
    max_results: int
    include_snippets: bool


def validate_search_goal(raw: object, goal_file: Path) -> EvidenceSearchGoal:
    fields = {"version", "kind", "goal", "sources", "terms",
              "max_results", "include_snippets"}
    if type(raw) is not dict or set(raw) != fields or (
        type(raw["version"]) is not int or raw["version"] != 1 or
        raw["kind"] != "local_evidence_search"
    ):
        raise ValueError("invalid versioned local_evidence_search goal")
    title = raw["goal"]
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(
        ord(c) < 32 for c in title
    ):
        raise ValueError("invalid local search goal title")
    names = raw["sources"]
    if type(names) is not list or not 1 <= len(names) <= 8:
        raise ValueError("local search requires 1-8 selected text files")
    root = goal_file.parent.resolve(strict=True)
    paths = []
    for supplied in names:
        if type(supplied) is not str or not 1 <= len(supplied) <= 512 or any(
            ch in "\\:" or ord(ch) < 32 for ch in supplied
        ):
            raise ValueError("source must be a short local relative filename")
        loc = Path(supplied)
        if loc.is_absolute() or ".." in loc.parts:
            raise ValueError("source path traversal forbidden")
        if loc.suffix.lower() not in (".md", ".txt"):
            raise ValueError("source must be .txt or .md")
        resolved = (root / loc).resolve(strict=True)
        if not resolved.is_relative_to(root) or resolved.suffix.lower() not in (".md", ".txt"):
            raise ValueError("source must be in goal directory and .txt/.md")
        if resolved in paths or any(x.name == resolved.name for x in paths):
            raise ValueError("duplicate or ambiguous source filename")
        paths.append(resolved)
    terms = raw["terms"]
    if type(terms) is not list or not 1 <= len(terms) <= 5 or any(
        type(t) is not str or not 1 <= len(t) <= 32 or not TERM_RE.fullmatch(t)
        for t in terms
    ):
        raise ValueError("search requires 1-5 exact terms")
    folded = tuple(t.casefold() for t in terms)
    if len(set(folded)) != len(folded):
        raise ValueError("search terms must be unique")
    if type(raw["max_results"]) is not int or not 1 <= raw["max_results"] <= 20:
        raise ValueError("max_results must be 1-20 integer")
    if type(raw["include_snippets"]) is not bool:
        raise ValueError("include_snippets must be a boolean")
    return EvidenceSearchGoal(title.strip(), root, tuple(paths), folded,
                              raw["max_results"], raw["include_snippets"])


def source_snapshot(path: Path) -> tuple[bytes, str]:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("source text file must be <=256 KiB")
    with path.open("rb") as file:
        binary = file.read(MAX_FILE_BYTES + 1)
    if len(binary) > MAX_FILE_BYTES:
        raise ValueError("source exceeds 256 KiB")
    return binary, hashlib.sha256(binary).hexdigest()


def text_lines(binary: bytes) -> list[str]:
    decoded = binary.decode("utf-8-sig")
    if "\x00" in decoded:
        raise ValueError("binary text sources are not accepted")
    lines = decoded.splitlines()
    if len(lines) > MAX_LINES or any(len(line) > MAX_LINE_LENGTH for line in lines):
        raise ValueError("source exceeds line or character bounds")
    return lines


def tokenize(line: str) -> list[str]:
    return [m.group().casefold() for m in TOKEN_RE.finditer(line)]


def _score(words: list[str], terms: tuple[str, ...]) -> int:
    # The entire term set must occur on the same source line. Phrase bonus
    # rewards exact adjacent terms in the user-specified order.
    if not set(terms).issubset(words):
        return 0
    freq = sum(words.count(term) for term in terms)
    phrase = any(tuple(words[i:i + len(terms)]) == terms
                 for i in range(len(words) - len(terms) + 1))
    return min(1000, freq) + (5 if phrase and len(terms) > 1 else 0)


def execute_search_goal(goal: EvidenceSearchGoal) -> dict:
    if type(goal) is not EvidenceSearchGoal:
        raise ValueError("unvalidated evidence search goal")
    provenance, found = [], []
    for file_index, path in enumerate(goal.sources):
        binary, digest = source_snapshot(path)
        lines = text_lines(binary)
        provenance.append({"filename": path.name, "sha256": digest,
                           "lines": len(lines)})
        for number, line in enumerate(lines, start=1):
            score = _score(tokenize(line), goal.terms)
            if score:
                found.append((score, file_index, number,
                              line[:160] if goal.include_snippets else None))
        if source_snapshot(path)[1] != digest:
            raise ValueError("evidence source changed during scan")
    found.sort(key=lambda row: (-row[0], row[1], row[2]))
    matches = [{"filename": provenance[file_index]["filename"],
                "line": line, "score": score, "excerpt": excerpt}
               for score, file_index, line, excerpt in found[:goal.max_results]]
    for path, record in zip(goal.sources, provenance):
        if source_snapshot(path)[1] != record["sha256"]:
            raise ValueError("evidence source changed across scans")
    return {
        "version": VERSION, "kind": "local_evidence_search",
        "goal": goal.goal, "status": "AGREE" if found else "UNAVAILABLE",
        "terms": list(goal.terms), "max_results": goal.max_results,
        "include_snippets": goal.include_snippets,
        "sources": provenance, "matching_lines": len(found),
        "matches": matches, "scope": SCOPE
    }


def render_search(report: dict) -> str:
    lines = ["EAI 로컬 증거 검색: " + report["status"],
             "전체 일치 줄: " + str(report["matching_lines"])]
    for item in report["matches"]:
        lines.append(f"{item['filename']}:{item['line']} (score={item['score']})")
        if item["excerpt"] is not None:
            lines.append("  " + item["excerpt"])
    return "\n".join(lines + [report["scope"]])
