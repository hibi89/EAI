"""User-facing labels for typed CPU, policy and verification outcomes."""
from datetime import datetime

PAGES = {
    "home": ("워크스페이스", "Workspace", "\ue80f"),
    "architect": ("설계 스튜디오", "Architect Studio", "\ue943"),
    "atlas": ("노드 탐색기", "AXNODE Atlas", "\ue8fd"),
    "player": ("시뮬레이션", "Player", "\ue768"),
    "verifier": ("영수증 검증", "Verifier", "\ue9f9"),
    "history": ("작업 기록", "History", "\ue81c"),
    "settings": ("설정 및 보안", "Settings", "\ue713"),
}
OPS = {"command": "CPU 명령", "example": "로컬 예제 열기", "draft_open": "설계 초안 열기",
       "draft_save": "설계 초안 저장", "design": "설계 대안 비교", "catalog": "AXNODE 검색",
       "node": "노드 상세", "plan": "계획 검토", "simulate": "순수 시뮬레이션",
       "verify": "영수증 검사", "settings": "예산 저장", "journey": "설계 영수증 재계산"}
STATUSES = {
    "OK": "완료", "ERROR": "입력 계산 실패", "DENIED": "권한 거부", "UNAVAILABLE": "자료 없음",
    "INPUT_INVALID": "입력 형식 확인 필요", "FILE_UNAVAILABLE": "파일을 열 수 없음",
    "LOCAL_STORE_ERROR": "로컬 데이터베이스 오류", "LOCAL_OPERATION_FAILED": "로컬 작업 실패",
    "HOLD_UNSUPPORTED_REQUEST": "지원 범위 밖의 요청", "HOLD_EXPLICIT_NOTE_APPROVAL": "메모 승인 대기",
    "HOLD_NOTE_NOT_APPROVED": "메모 저장 취소", "HOLD_NO_REMOTE_OR_LOCAL_SEARCH_CONFIGURED": "외부 검색 꺼짐",
    "HOLD_POLICY_DENIED": "정책상 실행 보류", "HOLD_PLAN_CHANGED": "입력 변경 · 재검토 필요",
    "HOLD_PURE_SIMULATION_CONFIRMATION": "시뮬레이션 승인 대기", "DRAFT_OPENED": "초안 열림",
    "DRAFT_SAVED": "새 초안 저장됨", "EXAMPLE_READY": "연습 자료 준비됨",
    "CANDIDATES_UNVERIFIED": "설계 대안 생성 · 검토 필요", "PARTIAL_UNVERIFIED": "일부 대안만 생성됨",
    "BLOCKED": "설계 보류", "BLOCKED_EVIDENCE_DISPUTE": "근거 충돌 · 설계 보류",
    "CANCELLED": "탐색 중단됨", "LOCAL_CATALOG_UNVERIFIED": "읽기 전용 목록",
    "NODE_DIGEST_MATCH": "노드 원문 SHA 일치", "PURE_SYNTHETIC_PREVIEW_ONLY": "순수 모의 실행 가능",
    "PURE_SYNTHETIC_INTERPRETED_UNVERIFIED": "모의 실행 완료", "PURE_SYNTHETIC_CANCELLED_NOT_EXECUTED": "지정 단계에서 중단",
    "LOCAL_JOURNEY_DIGEST_INTEGRITY_UNVERIFIED": "영수증 무결성 일치", "RECEIPT_DIGEST_MISMATCH": "영수증 SHA 불일치",
    "RECEIPT_CONTRACT_REJECTED": "영수증 계약 거부", "SETTINGS_SAVED": "예산 저장됨",
}
ERROR_TEXT = {"INPUT_INVALID": "입력의 형식, 범위 또는 자료의 무결성을 확인해 주세요.",
              "FILE_UNAVAILABLE": "선택한 파일의 위치와 로컬 읽기 권한을 확인해 주세요.",
              "LOCAL_STORE_ERROR": "저장소가 사용 중이거나 형식이 다릅니다. 원본을 보존하고 다시 선택하세요.",
              "LOCAL_OPERATION_FAILED": "작업 기록의 진단 코드로 실패를 확인할 수 있습니다."}


def caption(code):
    return STATUSES.get(code, code)


def timestamp(epoch):
    return datetime.fromtimestamp(epoch).strftime("%m.%d  %H:%M:%S")


def explain(op, result):
    code = result["status"]
    if "text" in result:
        return result["text"]
    if code in ERROR_TEXT:
        return ERROR_TEXT[code]
    if op == "design":
        u = result["uncertainty"]
        lines = [f"검색 확장 {result['expansions']}회   ·   미확인 {u['unknown_count']}건   ·   충돌 {u['contradiction_count']}건",
                 "로컬 자료에서 제안한 설계입니다. 가정과 현실 적합성은 별도 검토가 필요합니다."]
        for i, item in enumerate(result["alternatives"], 1):
            lines += ["", f"대안 {i}   {item['alternative_id']}", f"{item['step_count']}단계   ·   " + ", ".join(item["operator_ids"]),
                      *["근거 SHA-256   " + s for s in item["source_sha256"]]]
        lines.extend(["", "목표 SHA-256   " + result["problem_sha256"]])
        return "\n".join(lines)
    if op == "plan":
        lines = [f"위험도 {result['risk']}   ·   요청 권한 {', '.join(result['permissions'])}",
                 f"계획 예산 {result['budget'][0]}단계 / {result['budget'][1]}초"]
        for sid, operator, dependencies, capability in result["steps"]:
            lines.append(f"{sid}   ·   {operator}   ·   {capability}   ·   선행 {', '.join(dependencies) or '없음'}")
        lines += [*result["reasons"], "", "계획 SHA-256   " + result["plan_sha256"]]
        return "\n".join(lines)
    if op == "simulate" and "interpreted_steps" in result:
        return "\n".join([f"관찰된 모의 단계 {result['interpreted_steps']}개   ·   외부 작업 {result['external_actions']}건   ·   원본 쓰기 {result['original_writes']}건",
                          "재계산 결과   " + result["replay"], "보상 작업   해당 없음 · 원본 변경 없음",
                          *result["reasons"], "추적 SHA-256   " + (result["trace_sha256"] or "생성되지 않음")])
    if op in ("verify", "journey"):
        lines = ["검사 대상   선택한 로컬 Journey JSON", "기록된 SHA-256   " + (result.get("receipt_sha256") or "형식 오류"),
                 "재계산 SHA-256   " + result["calculated_sha256"]]
        if "candidate_count" in result:
            lines += [f"계약 검사 통과   ·   후보 {result['candidate_count']}개   ·   충돌 {result['conflict_count']}건   ·   미확인 {result['unknown_count']}건",
                      "목표 SHA-256   " + result["problem_sha256"]]
        lines.append("원본 작성자 인증과 현실 정답 검증은 미확인입니다.")
        return "\n".join(lines)
    if op == "node":
        return "\n".join([f"{result['node_id']}   ·   v{result['version']}   ·   {result['node_status']}",
                          f"신고된 출처 {result['source']}   ·   작성자 {result['author']}   ·   출력 {result['output']}",
                          "SHA-256   " + result["sha256"], "계보와 원문 해시가 일치합니다. 출처의 신뢰도는 미확인입니다."])
    return caption(code)
