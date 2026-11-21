"""Small shared primitives for filesystem boundaries and durable writes."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import tempfile
import time


class ExamError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def digest(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return digest(Path(path).read_bytes())


def inside(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ExamError("unsafe_path", "只允许项目内的相对路径")
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise ExamError("unsafe_path", "路径超出项目目录")
    return target


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def lock(path, timeout=10):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ExamError("locked", "目录正在写入；若进程已异常退出，请先备份并确认没有运行进程再移除锁文件")
            time.sleep(0.05)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def local_now():
    return datetime.now().astimezone()
