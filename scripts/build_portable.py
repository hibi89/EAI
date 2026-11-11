"""P27 deterministic stdlib portable .pyz packaging; explicit new output only.

Only eai Python source is embedded. No .env, private data, prompt history, model
weights, tests, customer examples, network calls or third-party dependencies.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

BUNDLE_VERSION = "eai.portable.v1"
ENTRY = (
    "from eai.__main__ import main\n"
    "if __name__ == '__main__':\n"
    "    raise SystemExit(main())\n"
)
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def _zip_info(path: str) -> ZipInfo:
    info = ZipInfo(path, date_time=FIXED_TIME)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    return info


def build_portable(source_root: str | Path, output: str | Path) -> dict:
    """Emit reproducible Python zipapp; refuse overwrite or source escapes."""
    folder = Path(source_root).expanduser().resolve(strict=True)
    package = folder / "eai"
    if not package.is_dir():
        raise ValueError("source must contain an eai Python package")
    target = Path(output).expanduser().absolute()
    if target.suffix.lower() != ".pyz":
        raise ValueError("output must be an explicit .pyz filename")
    if not target.parent.is_dir():
        raise ValueError("output directory must already exist")
    if target.exists() or target.is_symlink():
        raise FileExistsError("refusing to overwrite existing portable bundle")
    files = sorted(package.rglob("*.py"), key=lambda x: x.relative_to(folder).as_posix())
    if not files or not (package / "__init__.py").is_file():
        raise ValueError("invalid EAI package source")
    entries = [("__main__.py", ENTRY.encode("utf-8"))]
    for path in files:
        relative = path.relative_to(folder).as_posix()
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(folder):
            raise ValueError("refuse symlink or escaped Python source")
        data = path.read_bytes()
        if len(data) > 512 * 1024:
            raise ValueError("Python source file exceeds size bound")
        entries.append((relative, data))
    with TemporaryDirectory(prefix="eai_portable_") as temp:
        stage = Path(temp) / "eai.pyz"
        with ZipFile(stage, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(_zip_info(name), data)
        with ZipFile(stage) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != {
                name for name, _ in entries
            }:
                raise ValueError("portable ZIP failed independent integrity check")
        expected = hashlib.sha256(stage.read_bytes()).hexdigest()
        try:
            with stage.open("rb") as original, target.open("xb") as final:
                shutil.copyfileobj(original, final)
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError("portable output digest mismatch")
        except BaseException:
            # We have created the output exclusively, so removal cannot delete
            # any pre-existing user file. Do not retry in place.
            if target.is_file() and not target.is_symlink():
                target.unlink()
            raise
    return {
        "version": BUNDLE_VERSION, "filename": target.name,
        "sha256": expected, "source_modules": len(files),
        "bytes": target.stat().st_size,
        "scope": "Python 3.11+ required; no bundled runtime/model or Windows verification.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build EAI offline .pyz, no overwrite")
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_portable(args.source_root, args.output)
    except (ValueError, OSError, UnicodeError) as exc:
        print("EAI PORTABLE ERROR:", type(exc).__name__, str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
