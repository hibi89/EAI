"""P37 real Windows CMD acceptance harness for unsigned synthetic EAI ZIP.

Runs only on an explicitly acknowledged Windows host.  Does not use model,
customer files, network, installation, existing owner output paths or paid APIs.
Output JSON is an evidence summary, NOT antivirus, legal or buyer certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from scripts.build_customer_candidate import NAME, build
from scripts.verify_customer_candidate import PREFIX, verify_archive, verify_directory
from eai.customer_review import verify_review

VERSION = "eai.windows_candidate_acceptance.v1"
RELEASE_APPROVED = False


def _is_windows() -> bool:
    return os.name == "nt"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_cmd(script: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd.exe", "/d", "/c", str(script), "--ci"],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=70, check=False,
    )


def accept_windows_candidate(*, acknowledge: bool = False) -> dict:
    """Real cmd.exe journey with synthetic data; fail closed on any uncertainty."""
    if acknowledge is not True:
        return {"status": "BLOCKED", "code": "WINDOWS_HOST_ACK_REQUIRED"}
    if not _is_windows():
        return {"status": "BLOCKED", "code": "NATIVE_WINDOWS_NOT_AVAILABLE"}
    with TemporaryDirectory(prefix="eai-windows-accept-") as tmp:
        root = Path(tmp) / "한글 경로 EAI"
        root.mkdir()
        archive = root / NAME
        built = build(archive)
        checksum = root / (NAME + ".sha256")
        verified = verify_archive(archive, checksum)
        if built["sha256"] != verified["sha256"]:
            return {"status": "REJECTED", "code": "PACKAGE_HASH_MISMATCH"}
        extracted = root / "unpacked"
        with ZipFile(archive) as z:
            z.extractall(extracted)
        app = extracted / PREFIX.rstrip("/")
        before = {name: _digest(app / name) for name in (
            "eai.pyz", "verify_candidate.py", "RUN_EAI_REVIEW.cmd",
            "CUSTOMER_REVIEW_README.md", "MANIFEST.json",
            "samples/sample_key_coverage_goal.json",
            "samples/sample_master_keys.csv", "samples/sample_detail_keys.csv")}
        if verify_directory(app)["status"] != "CANDIDATE_DIRECTORY_CONSISTENT_UNSIGNED":
            return {"status": "REJECTED", "code": "EXTRACTION_MISMATCH"}
        first = _run_cmd(app / "RUN_EAI_REVIEW.cmd", root)
        if first.returncode != 0:
            return {"status": "REJECTED", "code": "WINDOWS_CMD_FAILED",
                    "exit_code": first.returncode}
        output = extracted / "EAI-SYNTHETIC-REVIEW"
        if verify_review(output)["status"] != "REVIEW_CONSISTENT_UNSIGNED":
            return {"status": "REJECTED", "code": "REVIEW_VERIFICATION_FAILED"}
        report = (output / "review.json").read_text(encoding="utf-8")
        html = (output / "review.html").read_text(encoding="utf-8")
        if any(secret in report + html for secret in ("sku_a", "line_1", "item_ref")):
            return {"status": "REJECTED", "code": "SYNTHETIC_KEY_LEAK"}
        if ('Content-Security-Policy' not in html or
                "<script" in html.lower() or "<iframe" in html.lower()):
            return {"status": "REJECTED", "code": "OFFLINE_HTML_POLICY_FAILED"}
        preserved = {p.name: _digest(p) for p in output.iterdir() if p.is_file()}
        repeat = _run_cmd(app / "RUN_EAI_REVIEW.cmd", root)
        if repeat.returncode != 2:
            return {"status": "REJECTED", "code": "NO_OVERWRITE_GATE_FAILED",
                    "exit_code": repeat.returncode}
        after = {p.name: _digest(p) for p in output.iterdir() if p.is_file()}
        if preserved != after:
            return {"status": "REJECTED", "code": "OUTPUT_MUTATED_ON_REPEAT"}
        if any(_digest(app / name) != digest for name, digest in before.items()):
            return {"status": "REJECTED", "code": "PACKAGE_MUTATED"}
        if verify_directory(app)["status"] != "CANDIDATE_DIRECTORY_CONSISTENT_UNSIGNED":
            return {"status": "REJECTED", "code": "PACKAGE_VERIFICATION_CHANGED"}
        return {"version": VERSION, "status": "PASS", "scope": "NATIVE_CMD_SYNTHETIC",
                "zip_sha256": built["sha256"], "windows_cmd": "PASS",
                "korean_space_path": "PASS", "repeat_no_overwrite": "PASS",
                "source_free_html_json": "PASS", "originals_modified": False,
                "real_qwen_tested": False, "customer_device_approved": False,
                "release_approved": RELEASE_APPROVED}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Synthetic-only native Windows candidate acceptance")
    p.add_argument("--ack-windows-host", action="store_true",
                   help="explicitly allow isolated temporary synthetic CMD execution on Windows")
    args = p.parse_args(argv)
    try:
        result = accept_windows_candidate(acknowledge=args.ack_windows_host)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired,
            KeyError, TypeError, EOFError) as exc:
        result = {"status": "REJECTED", "code": "WINDOWS_ACCEPTANCE_ERROR",
                  "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {"PASS": 0, "REJECTED": 2, "BLOCKED": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
