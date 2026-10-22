#!/usr/bin/env python3
"""Build BSL modules as EPFs and collect their output using a local 1C installation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "launcher_1c"


class LaunchError(Exception):
    """An unsuccessful build, process, or result exchange."""


POST_CREATE_DIRECTIVE = "// NativePostCreate: ExportProbeAfterCreate"


def post_create_requested(source: str) -> bool:
    """A visible fixed test-driver action, never an executable routine name."""
    lines = source.removeprefix("\ufeff").splitlines()
    directives = [(index, line) for index, line in enumerate(lines)
                  if re.match(r"\s*//\s*NativePostCreate", line)]
    if not directives:
        return False
    if directives != [(0, POST_CREATE_DIRECTIVE)]:
        raise LaunchError("Invalid NativePostCreate directive")
    return True


@dataclass(frozen=True)
class Platform:
    executable: Path
    database: Path
    timeout: float = 180
    user: str | None = None
    password: str | None = None

    def command(self, mode: str) -> list[str]:
        arguments = [str(self.executable), mode, "/F", str(self.database)]
        if self.user is not None:
            arguments.extend(["/N", self.user])
        if self.password is not None:
            arguments.extend(["/P", self.password])
        arguments.extend(["/AppAutoCheckVersion-", "/DisableStartupDialogs",
                          "/DisableStartupMessages", "/L", "ru"])
        return arguments


def validate_executable(executable: Path) -> Path:
    """Validate an explicitly selected platform file without guessing its edition."""
    if not executable.is_file():
        raise LaunchError(f"Нет исполняемого файла платформы 1С: {executable}")
    if os.name != "nt" and not os.access(executable, os.X_OK):
        raise LaunchError(f"Нет права на исполнение: {executable}")
    return executable.resolve()


def find_platform(directory: Path) -> Path:
    """Accept a platform's bin/version directory or a macOS application directory."""
    if not directory.is_dir():
        raise LaunchError(f"Нет директории платформы 1С: {directory}")
    names = ("1cv8.exe", "1cv8") if os.name == "nt" else ("1cv8", "1cv8.exe")
    roots = [directory, directory / "bin", directory / "Contents" / "MacOS"]
    roots.extend(sorted(directory.glob("*.app/Contents/MacOS")))
    candidates = [root / name for root in roots for name in names]
    for candidate in candidates:
        if candidate.is_file():
            return validate_executable(candidate)
    raise LaunchError(
        f"В {directory} не найден 1cv8/1cv8.exe. "
        "Укажите bin конкретной версии платформы с Конфигуратором и толстым клиентом."
    )


def read_platform_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def stop_process(process: subprocess.Popen) -> None:
    """Stop only the process tree started for this operation."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_process(command: list[str], directory: Path, log: Path, timeout: float) -> None:
    # Lists of arguments preserve spaces/Unicode without a shell or manual quoting.
    with log.open("wb") as output:
        with subprocess.Popen(
            command, cwd=directory, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT,
            start_new_session=os.name != "nt",
        ) as process:
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                stop_process(process)
                raise LaunchError(f"Истек таймаут {timeout:g} с. Лог: {log}") from None
            except KeyboardInterrupt:
                stop_process(process)
                raise
    if returncode:
        raise LaunchError(f"1С завершилась с кодом {returncode}. Лог: {log}")


def build_epf(platform: Platform, source: Path, destination: Path) -> None:
    log = destination.with_suffix(".designer.log")
    result = destination.with_suffix(".build-result.txt")
    command = platform.command("DESIGNER") + [
        "/LoadExternalDataProcessorOrReportFromFiles", str(source), str(destination),
        "/Out", str(log), "/DumpResult", str(result),
    ]
    run_process(command, destination.parent, destination.with_suffix(".designer-console.log"),
                platform.timeout)
    # Some platform errors do not produce a nonzero process exit code.
    if not result.is_file() or read_platform_text(result).strip() != "0":
        raise LaunchError(f"Конфигуратор не подтвердил успешную сборку. Лог: {log}")
    if not destination.is_file() or destination.stat().st_size == 0:
        raise LaunchError(f"Конфигуратор не создал {destination}. Лог: {log}")


def read_result(path: Path) -> tuple[list[str], str]:
    if not path.is_file():
        raise LaunchError(
            "1С не создала result.json: обработка запуска не выполнилась. "
            "Проверьте enterprise.log, права на внешние обработки и параметры входа."
        )
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, ValueError) as error:
        raise LaunchError(f"Не удалось прочитать result.json: {error}") from error
    if (not isinstance(result, dict)
            or not isinstance(result.get("messages"), list)
            or not all(isinstance(message, str) for message in result["messages"])
            or not isinstance(result.get("error"), str)):
        raise LaunchError("Некорректный формат result.json: нужны messages (массив строк) и error.")
    return result["messages"], result["error"]


def write_output(path: Path, messages: list[str]) -> None:
    # Match console output: UTF-8 without BOM, LF, one terminator per message.
    text = "".join(message.replace("\r\n", "\n").replace("\r", "\n") + "\n"
                   for message in messages)
    temporary = path.with_suffix(".out.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def run_case(platform: Platform, script: Path, launcher: Path,
             directory: Path, output: Path) -> None:
    source_text = script.read_text(encoding="utf-8-sig")
    post_create = post_create_requested(source_text)
    directory.mkdir()
    sources = directory / "src"
    shutil.copytree(TEMPLATES, sources)
    module = sources / "TestModule" / "Ext" / "ObjectModule.bsl"
    # Preserve all code including declarations, directives and the module body.
    module.write_text(source_text, encoding="utf-8-sig")
    epf = directory / "TestModule.epf"
    build_epf(platform, sources / "TestModule.xml", epf)

    result = directory / "result.json"
    request = directory / "request.json"
    request.write_text(json.dumps({"module": str(epf), "result": str(result),
                                   "post_create": post_create},
                                  ensure_ascii=False), encoding="utf-8")
    command = platform.command("ENTERPRISE") + [
        "/RunModeManagedApplication", "/VL", "ru_RU",
        "/Execute", str(launcher), "/C", str(request),
        "/Out", str(directory / "enterprise.log"),
    ]
    run_process(command, directory, directory / "enterprise-console.log", platform.timeout)
    messages, error = read_result(result)
    write_output(output, messages)
    if error:
        raise LaunchError(error)


def collect_scripts(directory: Path) -> list[Path]:
    scripts = sorted((path for path in directory.iterdir()
                      if path.is_file() and path.suffix.lower() == ".bsl"),
                     key=lambda path: (path.name.casefold(), path.name))
    if not scripts:
        raise LaunchError(f"В {directory} нет .bsl-тестов.")
    names: set[str] = set()
    for script in scripts:
        name = script.stem.casefold()
        if name in names:
            raise LaunchError(f"Имена тестов совпадают без учета регистра: {script.name}")
        names.add(name)
    return scripts


def run_suite(platform: Platform, root: Path = ROOT) -> int:
    scripts = collect_scripts(root / "tests")
    output = root / "output"
    output.mkdir(exist_ok=True)
    work = root / ".work"
    work.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=work)).resolve()
    print(f"Логи и временные обработки: {directory}", flush=True)

    # Remove previous results so a failed run cannot look like a successful old one.
    for script in scripts:
        for suffix in (".out", ".err"):
            (output / (script.stem + suffix)).unlink(missing_ok=True)

    launcher_sources = directory / "launcher_src"
    shutil.copytree(TEMPLATES, launcher_sources)
    launcher = directory / "Launcher.epf"
    print("Сборка обработки запуска...", flush=True)
    build_epf(platform, launcher_sources / "Launcher.xml", launcher)

    failed = 0
    for index, script in enumerate(scripts, 1):
        print(f"[{index}/{len(scripts)}] {script.name}", flush=True)
        case_directory = directory / f"test-{index:04d}"
        try:
            run_case(platform, script, launcher, case_directory,
                     output / (script.stem + ".out"))
        except (LaunchError, OSError, UnicodeError) as error:
            failed += 1
            message = f"{error}\nЛоги: {case_directory}\n"
            (output / (script.stem + ".err")).write_text(message, encoding="utf-8")
            print(f"  ОШИБКА: {message}", file=sys.stderr, flush=True)
        else:
            print(f"  OK -> {output / (script.stem + '.out')}", flush=True)
    print(f"Обработано: {len(scripts)}. Успешно: {len(scripts) - failed}. Ошибок: {failed}.")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Собрать BSL-тесты в EPF, запустить в 1С и сохранить вывод в output.")
    parser.add_argument("--bd", required=True, type=Path, help="Каталог существующей файловой базы")
    platform_options = parser.add_mutually_exclusive_group(required=True)
    platform_options.add_argument("--path-1c", type=Path,
                                  help="Каталог bin конкретной версии 1С (1cv8/1cv8.exe)")
    platform_options.add_argument("--executable-1c", type=Path,
                                  help="Точный путь к исполняемому файлу 1С, включая учебную 1cv8t")
    parser.add_argument("--timeout", type=float, default=180,
                        help="Таймаут каждого процесса 1С в секундах (по умолчанию 180)")
    parser.add_argument("--user", help="Имя пользователя базы, если требуется")
    parser.add_argument("--password", default=os.environ.get("YADINASSI_1C_PASSWORD"),
                        help="Пароль базы; также можно задать YADINASSI_1C_PASSWORD")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout должен быть положительным конечным числом")
    database = args.bd.expanduser().resolve()
    if not (database / "1Cv8.1CD").is_file():
        parser.error(f"Не найдена файловая база {database / '1Cv8.1CD'}")
    if args.password is not None and args.user is None:
        parser.error("Для пароля нужно указать --user")
    try:
        if args.executable_1c is not None:
            executable = validate_executable(args.executable_1c.expanduser().resolve())
        else:
            executable = find_platform(args.path_1c.expanduser().resolve())
        return run_suite(Platform(executable, database, args.timeout, args.user, args.password))
    except (LaunchError, OSError, UnicodeError) as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Запуск прерван.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
