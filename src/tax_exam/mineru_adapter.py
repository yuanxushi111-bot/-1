"""MinerU subprocess adapter: explicit remote choice, resumable local conversion jobs."""
from pathlib import Path
from urllib.parse import quote
import json
import os
import re
import shutil
import subprocess
import sys

from .common import ExamError, digest, file_hash, inside, load_json, lock, write_json


def environment(root):
    home = inside(root, "userdata/mineru")
    # CPython 3.13+ on Windows implements mode=0700 as a private directory DACL.
    # MinerU refuses credential files in a directory writable by other accounts.
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Keep the bundle independent of a machine's existing MinerU server/credentials.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("MINERU_")}
    env.update(MINERU_HOME=str(home), MINERU_TELEMETRY_DISABLED="1", MINERU_DOCLIB_TCP_HOST="127.0.0.1", MINERU_DOCLIB_TCP_PORT="0", MINERU_MODEL_SOURCE="local", PYTHONIOENCODING="utf-8")
    if not (Path(root) / "runtime-mineru/python.exe").exists():
        # Source-only installs use a normal Python interpreter; its children need the target path.
        env["PYTHONPATH"] = str(Path(root).resolve() / "runtime-mineru/site-packages")
    return env


def command(root):
    root = Path(root).resolve()
    if (root / "runtime-mineru/site-packages/mineru").is_dir():
        portable = root / "runtime-mineru/python.exe"
        python = portable if sys.platform == "win32" and portable.exists() else Path(sys.executable)
        return [str(python), str(root / "scripts/mineru_entry.py")]
    executable = shutil.which("mineru")
    if not executable:
        raise ExamError("mineru_not_installed", "包内尚未准备MinerU，且系统中未找到；运行准备MinerU脚本后重试")
    return [executable]


def invoke(root, arguments, timeout=80):
    env = environment(root)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        process = subprocess.run(command(root) + arguments, capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=timeout, **options)
    except subprocess.TimeoutExpired:
        raise ExamError("mineru_timeout", "等待MinerU超时；任务保留，可稍后继续，不自动切换远程或降低质量")
    try:
        data = json.loads(process.stdout)
    except ValueError:
        raise ExamError("mineru_invalid_output", "MinerU未返回有效JSON；请检查解析环境，不回显可能含隐私的原始日志")
    if process.returncode and not data.get("error"):
        raise ExamError("mineru_failed", "MinerU执行失败，请检查版本和本地解析环境")
    return data


def check(root):
    try:
        version = invoke(root, ["version", "--json"], 20)
        value = version.get("mineru_version", "")
        if not re.match(r"^4\.", value):
            return {"installed": True, "compatible": False, "version": value, "message": "此适配器需要MinerU 4.x，不自动升级现有安装"}
        state = invoke(root, ["server", "status", "--json"], 25)
        # Do not print the raw server config: it may contain local endpoints or credentials.
        return {"installed": True, "compatible": True, "version": value, "environment": "bundled" if len(command(root)) > 1 else "system", "service_running": bool(state.get("running")), "service_check_error": state.get("error", {}).get("code"), "local_home": "userdata/mineru", "remote_default": False}
    except ExamError as error:
        return {"installed": False, "compatible": False, "error": {"code": error.code, "message": str(error)}}


def validate_export(path, response):
    text = Path(path).read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ExamError("empty_conversion", "转换结果为空，不能导入")
    markers = re.findall(r"<!-- page (\d+) of (\d+) -->", text)
    if markers:
        totals = {int(total) for _, total in markers}
        if len(totals) != 1 or {int(page) for page, _ in markers} != set(range(1, next(iter(totals)) + 1)):
            raise ExamError("incomplete_conversion", "导出页序不完整，不能把部分正文当作全文导入")
    elif isinstance(response.get("content"), dict) and response["content"].get("next_request"):
        raise ExamError("incomplete_conversion", "转换结果仍有未读取的后续内容，暂不导入")
    return text


def start_bundled_service(root):
    """Start only our project-local document service; never restart a user's service."""
    if len(command(root)) == 1:
        return False
    env = environment(root)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        # Initialize the private local auth file before the CLI's first status probe.
        prepare = subprocess.run([command(root)[0], "-c", "from mineru.config import load_doclib_server_config; load_doclib_server_config()"], capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=20, **options)
        if prepare.returncode:
            raise ExamError("mineru_private_config_failed", "无法初始化项目内私密解析配置；请检查目录权限")
        process = subprocess.run(command(root) + ["server", "start"], capture_output=True, encoding="utf-8", errors="replace", env=env, timeout=45, **options)
    except subprocess.TimeoutExpired:
        raise ExamError("mineru_service_starting", "本地解析服务仍在启动，稍后继续原任务；不自动重启服务")
    if process.returncode:
        raise ExamError("mineru_service_start_failed", "项目内解析服务启动失败；请检查本地服务日志，不影响已有学习资料")
    return True


def convert(root, path=None, tier=None, remote=False, resume=None):
    root = Path(root).resolve()
    if resume:
        if not re.fullmatch(r"task-[a-f0-9]{20}", resume):
            raise ExamError("invalid_job", "转换任务ID无效")
        job_dir = inside(root, "userdata/import-tasks/" + resume)
        state = load_json(job_dir / "task.json")
        original = job_dir / state["original_name"]
        tier, remote = state["tier"], state["remote"]
        if file_hash(original) != state["source_hash"]:
            raise ExamError("job_source_changed", "任务原件已变化，不能沿用旧转换任务")
    else:
        path = Path(path).resolve()
        if not path.is_file():
            raise ExamError("file_not_found", "找不到待转换文件")
        if path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return {"status": "direct_read", "output": str(path), "next_action": "无需OCR；使用import-material或import-markdown预览导入"}
        if tier not in (None, "basic", "standard", "advanced", "flash"):
            raise ExamError("invalid_tier", "未知解析档位")
        source_hash = file_hash(path)
        job_id = "task-" + digest(source_hash + str(tier) + str(remote) + path.suffix.lower())[:20]
        job_dir = inside(root, "userdata/import-tasks/" + job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        state_file = job_dir / "task.json"
        original_name = "original" + path.suffix.lower()
        original = job_dir / original_name
        if state_file.exists():
            state = load_json(state_file)
        else:
            shutil.copyfile(path, original)
            state = {"schema_version": 1, "id": job_id, "source_hash": source_hash, "original_name": original_name, "tier": tier, "remote": bool(remote), "status": "new"}
            write_json(state_file, state)
    with lock(job_dir / "convert.lock"):
        if state.get("status") == "done":
            output = job_dir / "converted.md"
            if file_hash(output) != state["output_hash"]:
                raise ExamError("conversion_changed", "已完成的转换正文被修改，请核对后另行导入，不重写该任务")
            return {**state, "output": str(output), "cached": True}
        output = job_dir / "converted.md"
        state.update(status="converting")
        write_json(job_dir / "task.json", state)
        try:
            args = ["parse", str(original), "--wait", "20", "--output", str(output), "--json"]
            if original.suffix.lower() == ".pdf":
                args.extend(["--pages", "all"])
            if tier:
                args.extend(["--tier", tier])
            if remote:
                args.append("--remote")
            response = invoke(root, args)
            if response.get("error", {}).get("code") == "server_not_running" and start_bundled_service(root):
                response = invoke(root, args)
            if response.get("error"):
                error = response["error"]
                code = error.get("code", "parse_failed")
                state.update(status="pending" if code in {"parse_wait_timeout", "parse_timeout"} else "failed", error_code=code)
                write_json(job_dir / "task.json", state)
                return {**state, "next_action": "稍后convert --resume此任务" if state["status"] == "pending" else "检查本地引擎/资源；远程或低质量解析须由使用者明确选择"}
            if not output.exists():
                state.update(status="pending")
                write_json(job_dir / "task.json", state)
                return {**state, "next_action": "稍后继续；尚无完整转换文件"}
            text = validate_export(output, response)
            assets = job_dir / "assets"
            locators = list(dict.fromkeys(re.findall(r"!\[[^\n]*?\]\((doc:[^)\s]+)\)", text)))
            for index, locator in enumerate(locators, 1):
                assets.mkdir(exist_ok=True)
                image = assets / f"image-{index}.png"
                if not image.exists():
                    result = invoke(root, ["read", locator, "--format", "image", "--output", str(image), "--json"])
                    if result.get("error") or not image.exists():
                        raise ExamError("asset_export_failed", "正文已生成，但图片尚未完整导出，请继续任务")
                text = text.replace("(" + locator + ")", "(" + quote(image.relative_to(job_dir).as_posix(), safe="/") + ")")
            output.write_text(text, encoding="utf-8")
            state.update(status="done", output_hash=file_hash(output), images=len(locators))
            state.pop("error_code", None)
            write_json(job_dir / "task.json", state)
            return {**state, "output": str(output), "next_action": "检查转换后使用import-material或整理为标准题库再导入；尚未自动成为答案库"}
        except (ExamError, OSError) as error:
            state.update(status="failed", error_code=getattr(error, "code", "io_error"))
            write_json(job_dir / "task.json", state)
            raise
