"""Bounded local file selection and isolated SQLite reads for the workstation."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from tempfile import TemporaryDirectory
import time


def local_path(value: str | Path, *, private: bool = False) -> Path:
    path = Path(value).expanduser()
    if ".." in path.parts:
        raise ValueError("parent traversal is not a local selection")
    if os.name == "nt":
        if (str(path).startswith(("\\\\", "//")) or path.is_reserved()
                or any(":" in p or p.endswith((" ", ".")) or Path(p).is_reserved()
                       for p in path.parts if p != path.anchor)):
            raise ValueError("ordinary local drive selection required")
        import ctypes
        # ctypes.windll exists only on Windows; fail closed if a purported
        # Windows host cannot provide the native drive-type verifier.
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise ValueError("native local disk verification unavailable")
        if windll.kernel32.GetDriveTypeW(Path(path.absolute().anchor).as_posix().replace("/", "\\")) not in (2, 3, 6):
            raise ValueError("local disk required")
    path = path.absolute()
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                or (private and stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
            raise ValueError("linked local selection denied")
    return path


def bounded_file(value: str | Path, limit: int) -> Path:
    path = local_path(value)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("bounded ordinary local file required")
    return path


def read_bytes(value: str | Path, limit: int) -> bytes:
    with bounded_file(value, limit).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file grew beyond its limit")
    return data


def _stamp(path: Path):
    local_path(path)
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("ordinary database files required")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _snapshot_digest(path: Path, size: int, output=None) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = size
        while remaining:
            chunk = stream.read(min(remaining, 256 * 1024))
            if not chunk:
                raise ValueError("database changed during snapshot")
            if output is not None:
                output.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.digest()


@contextmanager
def sqlite_snapshot(path: Path):
    """Read committed WAL data without opening SQLite on the original directory.

    Copy the bounded main file and WAL into a private directory, checking for
    a concurrent change. SQLite builds its own shared-memory index there.
    Idle and live WAL libraries are both supported; busy copies fail closed.
    """
    path = local_path(path)
    wal = Path(str(path) + "-wal")
    journal = Path(str(path) + "-journal")
    files = (path, wal, journal)
    before = tuple(_stamp(item) for item in files)
    cap = 64 * 1024 * 1024
    if before[0] is None or sum(s[2] for s in before if s) > cap or (before[2] and before[2][2]):
        raise ValueError("database unavailable, busy or above preview limit")
    with TemporaryDirectory(prefix="eai-read-") as folder:
        target = Path(folder) / "snapshot.sqlite"
        hashes = {}
        for original, dest, info in zip(files[:2], (target, Path(str(target) + "-wal")), before[:2]):
            if info is None:
                continue
            with dest.open("xb") as out:
                hashes[original] = _snapshot_digest(original, info[2], out)
        # Windows may defer last-write timestamps while a writer is open.
        # Recheck the bounded source bytes as well as its directory entries.
        for original, info in zip(files[:2], before[:2]):
            if info is not None and _snapshot_digest(original, info[2]) != hashes[original]:
                raise ValueError("database changed during snapshot")
        if tuple(_stamp(item) for item in files) != before:
            raise ValueError("database changed while reading")
        db = sqlite3.connect(target, timeout=1)
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
            deadline = time.monotonic() + 8
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 2500)
            yield db
        finally:
            db.close()
