"""CLI and incremental, stateful interactive console."""

import argparse
from pathlib import Path
import sys

from . import __version__
from .errors import BSLError, IncompleteInput
from .parser import parse
from .runtime import Interpreter
from .values import to_string


def repl(interpreter: Interpreter) -> int:
    interactive = sys.stdin.isatty()
    if interactive:
        print(f"yadinassi {__version__} — консоль 1С. :help — помощь, :exit — выход.")
    buffer = ""
    had_error = False
    while True:
        try:
            line = input(("... " if buffer else ">>> ") if interactive else "")
        except EOFError:
            if buffer:
                try:
                    interpreter.execute(buffer, "<консоль>")
                except BSLError as error:
                    print(error, file=sys.stderr)
                    had_error = True
            if interactive:
                print()
            return int(had_error)
        except KeyboardInterrupt:
            buffer = ""
            if interactive:
                print("\nВвод отменен.")
                continue
            return 130
        if not buffer and line.strip() in (":exit", ":quit"):
            return int(had_error)
        if not buffer and line.strip() == ":help":
            print("Введите код 1С. Блоки и скобки можно продолжать на следующих строках.\n"
                  "Выражения выводят значение; переменные сохраняются между командами.\n"
                  ":exit / :quit — выход; Ctrl+C — отмена ввода или исполнения.")
            continue
        buffer += line + "\n"
        try:
            program = parse(buffer, "<консоль>")
        except IncompleteInput:
            continue
        except (BSLError, RecursionError) as error:
            print(error, file=sys.stderr)
            had_error = True
            buffer = ""
            continue
        buffer = ""
        try:
            result = interpreter.execute_program(program)
            if result is not None:
                print(to_string(result))
        except BSLError as error:
            print(error, file=sys.stderr)
            had_error = True
        except KeyboardInterrupt:
            if not interactive:
                return 130
            print("\nИсполнение прервано.")


def main(argv: list[str] | None = None) -> int:
    # UTF-8 is also used for redirected streams and Windows consoles.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="yadinassi", description="Интерпретатор языка 1С (BSL)")
    parser.add_argument("file", nargs="?", help="файл BSL для исполнения; '-' — стандартный ввод")
    parser.add_argument("-c", "-с", "--command", help="код BSL для исполнения")
    parser.add_argument("--encoding", default="utf-8-sig", help="кодировка файла (по умолчанию UTF-8)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    if args.file is not None and args.command is not None:
        parser.error("файл и -c нельзя использовать одновременно")
    interpreter = Interpreter()
    try:
        if args.command is not None:
            interpreter.execute(args.command, "<команда>")
        elif args.file is not None:
            if args.file == "-":
                text = sys.stdin.read()
                source = "<stdin>"
            else:
                text = Path(args.file).read_text(encoding=args.encoding)
                source = args.file
            interpreter.execute(text, source)
        else:
            return repl(interpreter)
    except BSLError as error:
        print(error, file=sys.stderr)
        return 1
    except (OSError, UnicodeError, LookupError) as error:
        print(f"yadinassi: {error}", file=sys.stderr)
        return 1
    except RecursionError:
        print("yadinassi: превышена допустимая глубина вложенности кода", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nИсполнение прервано.", file=sys.stderr)
        return 130
    return 0
