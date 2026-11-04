"""CLI and incremental, stateful interactive console."""

import argparse
from pathlib import Path
import sys

from . import __version__
from .database_context import SQLiteDBContext
from .catalog_backend import BackendError
from .errors import BSLError, BSLRuntimeError, IncompleteInput
from .syntax.parser import parse
from .syntax.preprocessor import COMPILATION_PROFILES
from .runtime import Interpreter
from .values import to_string


_UNSUPPORTED_AUTH = "yadinassi: authentication options --user/--psw are not supported"
_EMPTY_DATABASE = "yadinassi: --f requires a non-empty SQLite file"


def _option_arguments(arguments: list[str]):
    """Visit options without interpreting BSL source or crossing ``--``."""
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return
        following = arguments[index + 1] if index + 1 < len(arguments) else None
        yield argument, following
        if argument in ("-c", "-с", "--command"):
            if following == "--":
                return
            index += 2
        else:
            index += 1


def _has_auth_option(arguments: list[str]) -> bool:
    """Reject credentials before argparse can echo values or exit for --help."""
    return any(argument.partition("=")[0] in ("--user", "--psw")
               for argument, _ in _option_arguments(arguments))


def _has_empty_database_option(arguments: list[str]) -> bool:
    return any(argument == "--f=" or (argument == "--f" and following == "")
               for argument, following in _option_arguments(arguments))


def repl(interpreter: Interpreter) -> int:
    interactive = sys.stdin.isatty()
    read_line = input
    if interactive:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory

        session = PromptSession(history=InMemoryHistory(), reserve_space_for_menu=0)
        read_line = session.prompt
        print(f"yadinassi {__version__} — Yet Another oDIN ASS Interpreter. /help — помощь, /exit — выход.")
    buffer = ""
    had_error = False
    while True:
        try:
            line = read_line(("... " if buffer else ">>> ") if interactive else "")
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
        if not buffer and line.strip() in ("/exit", "/quit"):
            return int(had_error)
        if not buffer and line.strip() == "/help":
            print("Введите код 1С. Блоки и скобки можно продолжать на следующих строках.\n"
                  "Выражения выводят значение; переменные сохраняются между командами.\n"
                  "←/→ — перемещение курсора; ↑/↓ — история команд текущего сеанса.\n"
                  "/exit / /quit — выход; Ctrl+C — отмена ввода или исполнения.")
            continue
        buffer += line + "\n"
        try:
            program = parse(buffer, "<консоль>", compilation_profile=interpreter.compilation_profile)
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
                try:
                    presentation = to_string(result)
                except (ValueError, TypeError, ArithmeticError) as error:
                    # Implicit REPL output is outside Interpreter.visit, but
                    # presentation limits still need recoverable diagnostics.
                    token = program[-1].token
                    raise BSLRuntimeError(str(error), token.source, token.line,
                                          token.column) from error
                print(presentation)
        except BSLError as error:
            print(error, file=sys.stderr)
            had_error = True
        except KeyboardInterrupt:
            interpreter.close()
            if not interactive:
                return 130
            print("\nИсполнение прервано.")


def main(argv: list[str] | None = None) -> int:
    # UTF-8 is also used for redirected streams and Windows consoles.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _has_auth_option(arguments):
        print(_UNSUPPORTED_AUTH, file=sys.stderr)
        return 2
    if _has_empty_database_option(arguments):
        print(_EMPTY_DATABASE, file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(prog="yadinassi", description="Интерпретатор языка 1С (BSL)",
                                     allow_abbrev=False)
    parser.add_argument("file", nargs="?", help="файл BSL для исполнения; '-' — стандартный ввод")
    parser.add_argument("-c", "-с", "--command", help="код BSL для исполнения")
    parser.add_argument("--f", metavar="SQLITE_FILE",
                        help="файл SQLite базы yadinassi с конфигурацией и данными")
    parser.add_argument("--create-db", metavar="SQLITE_FILE", help="создать новую SQLite базу из XML конфигурации")
    parser.add_argument("--import-xml", metavar="DIRECTORY", help="каталог штатной XML-выгрузки конфигурации")
    parser.add_argument("--inactive", action="store_true", help="сохранить конфигурацию без активации исполнения")
    parser.add_argument("--encoding", default="utf-8-sig", help="кодировка файла (по умолчанию UTF-8)")
    parser.add_argument("--preprocessor-profile", choices=COMPILATION_PROFILES, default="standalone",
                        help="профиль условной компиляции (по умолчанию standalone)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(arguments)
    if args.create_db is not None or args.import_xml is not None or args.inactive:
        if args.create_db is None or args.import_xml is None:
            parser.error("--create-db и --import-xml требуются вместе")
        if args.f is not None or args.file is not None or args.command is not None:
            parser.error("импорт конфигурации не совмещается с исполнением или --f")
        from .configuration_import import load_configuration_directory
        try:
            configuration = load_configuration_directory(args.import_xml)
        except (BackendError, ValueError, OSError):
            print("yadinassi: configuration import refused", file=sys.stderr)
            return 1
        try:
            context = SQLiteDBContext.create(args.create_db, configuration, activate=not args.inactive)
            context.close()
        except BackendError as error:
            if error.code == 'uncertain_commit':
                print("yadinassi: database creation outcome uncertain; preserve the destination and SQLite journal, and inspect them before retrying or deleting", file=sys.stderr)
            else:
                print("yadinassi: database creation failed; if a destination exists, preserve and inspect it before retrying or deleting", file=sys.stderr)
            return 1
        except (ValueError, OSError):
            print("yadinassi: database creation failed; if a destination exists, preserve and inspect it before retrying or deleting", file=sys.stderr)
            return 1
        print("Created inactive SQLite archive." if args.inactive else "Created SQLite database.")
        if args.inactive:
            for issue in configuration.activation_issues:
                print("Activation issue: " + issue)
        return 0
    if args.file is not None and args.command is not None:
        parser.error("файл и -c нельзя использовать одновременно")
    try:
        database_context = SQLiteDBContext(args.f) if args.f is not None else None
    except BackendError as error:
        print(f"yadinassi: database {error.code}", file=sys.stderr)
        return 1
    try:
        interpreter = Interpreter(encoding=args.encoding, database_context=database_context,
                                  compilation_profile=args.preprocessor_profile)
    except BackendError as error:
        if database_context is not None:
            database_context.close()
        print(f"yadinassi: database {error.code}", file=sys.stderr)
        return 1
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
            result = repl(interpreter)
            if result:
                return result
            interpreter.ensure_complete()
            return result
        interpreter.ensure_complete()
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
    finally:
        interpreter.close()
        if database_context is not None:
            database_context.close()
    return 0
