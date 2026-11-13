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
            if not interactive:
                interpreter.close()
                return 130
            interpreter.cancel_pending()
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
                                     allow_abbrev=False,
                                     epilog="UI: yadinassi --ui --f SQLITE_FILE [--open-browser]. The database must already grant a supported UI profile.")
    parser.add_argument("file", nargs="?", help="файл BSL для исполнения; '-' — стандартный ввод")
    parser.add_argument("-c", "-с", "--command", help="код BSL для исполнения")
    parser.add_argument("--f", metavar="SQLITE_FILE",
                        help="файл SQLite базы yadinassi с конфигурацией и данными")
    creation = parser.add_mutually_exclusive_group()
    creation.add_argument("--create-db", metavar="SQLITE_FILE", help="создать новую SQLite базу из XML конфигурации")
    creation.add_argument("--create-demo-db", metavar="SQLITE_FILE",
                          help="создать новую SQLite демо-базу из точных исходников демо: виды, склады, номенклатура")
    parser.add_argument("--import-xml", metavar="DIRECTORY", help="каталог штатной XML-выгрузки конфигурации")
    parser.add_argument("--numbering-policy", choices=("explicit", "decimal_v1"),
                        help="локальная политика нумерации при импорте; не гарантия совместимости с 1С")
    parser.add_argument("--module-runtime", choices=("managed-client-server-v1",),
                        help="явный runtime общих модулей и приложения; импорт не исполняет код")
    parser.add_argument("--inactive", action="store_true", help="сохранить конфигурацию без активации исполнения")
    parser.add_argument("--encoding", default="utf-8-sig", help="кодировка файла (по умолчанию UTF-8)")
    parser.add_argument("--preprocessor-profile", choices=COMPILATION_PROFILES, default="standalone",
                        help="профиль условной компиляции (по умолчанию standalone)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    from .configuration_profile_import import PROFILES
    parser.add_argument('--source-profile', choices=PROFILES,
                        help='explicit closed source grant; default legacy, never auto-detected')
    parser.add_argument('--check-xml', metavar='DIRECTORY',
                        help='read-only source/schema/compile preflight; creates no database')
    parser.add_argument('--report-json', action='store_true',
                        help='bounded machine-readable preflight report; requires --check-xml')
    parser.add_argument('--configuration-source', metavar='PATH',
                        help='экспериментальный источник XML/архив без активации базы')
    parser.add_argument('--save-source', metavar='ARCHIVE',
                        help='сохранить загруженный источник в проверяемый архив')
    parser.add_argument('--run-startup', action='store_true',
                        help='явно исполнить запуск источника без базы и UI')
    scratch = parser.add_mutually_exclusive_group()
    scratch.add_argument('--source-scratch-db', metavar='NEW_SQLITE_FILE',
                        help='создать отдельную новую базу констант для запуска источника')
    scratch.add_argument('--open-source-scratch-db', metavar='EXISTING_SQLITE_FILE',
                         help='открыть сохранённую базу источника; XML/архив необязателен, без миграции')
    scratch.add_argument('--update-source-scratch-db', metavar='EXISTING_SQLITE_FILE',
                         help='явно обновить источник scratch-базы без запуска кода; только совместимое добавление')
    parser.add_argument('--source-catalog-records', action='store_true',
                        help='явно использовать v4 scratch с записями справочников; v3 не мигрируется')
    parser.add_argument('--source-document-records', action='store_true',
                        help='явно использовать v5 scratch с непроведёнными документами и справочниками; старые базы не мигрируются')
    parser.add_argument('--source-compatibility-target', metavar='VERSION',
                        help='явный экспериментальный AppVersion target, не установленная версия 1С')
    args = parser.parse_args(arguments)
    if args.configuration_source is not None or args.open_source_scratch_db is not None or args.update_source_scratch_db is not None:
        if any((args.f, args.file, args.command, args.create_db, args.create_demo_db,
                args.import_xml, args.check_xml, args.source_profile, args.module_runtime,
                args.numbering_policy, args.inactive, args.report_json)):
            parser.error('--configuration-source не совмещается с режимами базы/профилей/BSL')
        if args.update_source_scratch_db is not None and (args.configuration_source is None or args.run_startup or args.save_source):
            parser.error('--update-source-scratch-db требует --configuration-source и отдельный запуск; --run-startup/--save-source несовместимы')
        if args.source_compatibility_target is not None and not args.run_startup:
            parser.error('--source-compatibility-target требует --run-startup')
        if (args.source_catalog_records or args.source_document_records) and not (args.source_scratch_db or args.open_source_scratch_db or args.update_source_scratch_db):
            parser.error('--source-catalog-records/--source-document-records требует scratch-базу')
        if (args.source_scratch_db or args.open_source_scratch_db) and not args.run_startup:
            parser.error('--source-scratch-db/--open-source-scratch-db требует --run-startup')
        from .configuration_source import load_source_directory, load_source_archive, save_source_archive
        from .configuration_source_runtime import SourceApplication
        application = None
        try:
            from .source_constant_store import SourceConstantStore
            if args.source_catalog_records:
                from .source_catalog_store import SourceCatalogStore
                SourceConstantStore = SourceCatalogStore
            if args.source_document_records:
                from .source_document_store import SourceDocumentStore
                SourceConstantStore = SourceDocumentStore
            if args.configuration_source is None:
                source = SourceConstantStore.load_source(args.open_source_scratch_db)
            else:
                path = Path(args.configuration_source)
                source = load_source_directory(path) if path.is_dir() else load_source_archive(path)
            if args.update_source_scratch_db is not None:
                result = SourceConstantStore.update_source(args.update_source_scratch_db, source)
                print('Источник scratch-базы обновлён; сохранено значений: ' + str(result['preserved_values']) + '; добавлено констант: ' + str(result['added_constants']) + '; SHA256: ' + result['source_sha256'] + '. Код не запускался.')
                return 0
            if args.save_source:
                save_source_archive(args.save_source, source)
            print('Источник загружен: ' + source.name + '; файлов: ' + str(len(source.files))
                  + ('. UI и обычная база конфигурации не активированы.' if args.source_scratch_db or args.open_source_scratch_db
                     else '. База данных и UI не активированы.'))
            if args.run_startup:
                application = SourceApplication(source, compilation_profile=args.preprocessor_profile,
                                                source_catalog_records=args.source_catalog_records,
                                                source_document_records=args.source_document_records,
                                                scratch_database=args.source_scratch_db,
                                                existing_scratch_database=args.open_source_scratch_db,
                                                compatibility_target=args.source_compatibility_target)
                if args.source_compatibility_target is not None:
                    print('Экспериментальный compatibility target: ' + args.source_compatibility_target
                          + '; фактический runtime: yadinassi ' + __version__
                          + '. Это не установленная 1С и не гарантия совместимости. '
                          + 'Строковые представления source-перечислений метаданных канонические XML, не native-локализация.', file=sys.stderr)
                started = application.start()
                print('Обработчики запуска завершены.' if started else 'Запуск отменён обработчиком.')
            return 0
        except (BSLError, ValueError, TypeError, OSError, RecursionError) as error:
            print('yadinassi: запуск/загрузка источника: ' + str(error), file=sys.stderr)
            return 1
        finally:
            if application is not None:
                application.close()
    if args.save_source or args.run_startup or args.source_scratch_db or args.open_source_scratch_db or args.source_catalog_records or args.source_document_records or args.source_compatibility_target is not None:
        parser.error('--save-source/--run-startup требует --configuration-source')

    demo = args.create_demo_db is not None
    main_demo = False
    from .configuration_diagnostics import from_exception
    if args.report_json and args.check_xml is None:
        parser.error('--report-json requires --check-xml')
    if args.check_xml is not None:
        if args.create_db is not None or demo or args.import_xml is not None or args.f is not None or args.file is not None or args.command is not None:
            parser.error('--check-xml cannot be combined with creation or execution')
        from .configuration_profile_import import prepare_directory
        import json
        try:
            prepared = prepare_directory(args.check_xml, profile=args.source_profile or 'legacy',
                numbering_policy=args.numbering_policy or 'explicit', module_runtime=args.module_runtime,
                activate=not args.inactive)
            report = prepared.report()
        except (BackendError, BSLError, ValueError, OSError) as error:
            report = {'format': 'configuration_preflight_v1', 'profile': args.source_profile or 'legacy',
                      'ready': False, 'diagnostics': [from_exception(error).as_dict()]}
        if args.report_json:
            print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        elif report['ready']:
            print('Configuration preflight ready: ' + report['profile'] + '; storage format ' + str(report['storage_format']) + '.')
        else:
            for diagnostic in report['diagnostics']:
                print('yadinassi: configuration import refused: ' + '; '.join(k+'='+str(v) for k,v in diagnostic.items()), file=sys.stderr)
        return 0 if report['ready'] else 1
    if args.source_profile is not None and args.create_db is None:
        parser.error('--source-profile requires --create-db or --check-xml')
    if args.create_db is not None or demo or args.import_xml is not None or args.inactive or args.numbering_policy is not None:
        if (args.create_db is None and not demo) or args.import_xml is None:
            parser.error("--create-db или --create-demo-db требуется вместе с --import-xml")
        if args.f is not None or args.file is not None or args.command is not None:
            parser.error("импорт конфигурации не совмещается с исполнением или --f")
        if demo and (args.inactive or args.numbering_policy is not None or args.module_runtime is not None):
            parser.error("--create-demo-db не совмещается с --inactive или --numbering-policy")
        from .configuration_import import read_configuration_directory
        from .configuration_profile_import import prepare_directory, create_prepared
        try:
            if demo:
                configuration = read_configuration_directory(args.import_xml)
                # The historical exact 19-file demo remains supported. A full
                # application manifest selects the new closed main-demo grant;
                # failure never falls back to weaker legacy admission.
                main_demo = 'InventoryApplication.xml' in configuration
                if main_demo:
                    from .configuration_profile_import import prepare_files
                    from .configuration_main_demo import PROFILE as MAIN_DEMO
                    prepared = prepare_files(configuration, profile=MAIN_DEMO)
            else:
                prepared = prepare_directory(args.import_xml, profile=args.source_profile or 'legacy',
                    numbering_policy=args.numbering_policy or 'explicit', module_runtime=args.module_runtime,
                    activate=not args.inactive)
                configuration = prepared.configuration
                if prepared.diagnostics:
                    from .configuration_diagnostics import ImportRefusal
                    raise ImportRefusal(prepared.diagnostics[0])
        except (BackendError, BSLError, ValueError, OSError) as error:
            diagnostic = from_exception(error)
            suffix = "" if diagnostic.code == "import_refused" else ": " + diagnostic.text()
            print("yadinassi: configuration import refused" + suffix, file=sys.stderr)
            return 1
        try:
            if demo:
                from .sqlite_catalog import SQLiteCatalogBackend
                context = (create_prepared(args.create_demo_db, prepared) if main_demo else
                           SQLiteCatalogBackend.create_demo_products(args.create_demo_db, configuration))
            else:
                context = create_prepared(args.create_db, prepared)
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
        if demo:
            print("Created main demo SQLite database: ВидыНоменклатуры, Склады, Номенклатура, Receipt, Issue, Stock, Units, States."
                  if main_demo else "Created demo SQLite database: ВидыНоменклатуры, Склады, Номенклатура.")
            print("Original demo handlers; bounded local editor, not native 1C managed-form parity.")
        else:
            print("Created inactive SQLite archive." if args.inactive else "Created SQLite database.")
        if args.inactive:
            from .configuration_diagnostics import activation_diagnostics
            for diagnostic in activation_diagnostics(configuration):
                print("Activation issue: " + diagnostic.text())
        return 0
    if args.module_runtime is not None and args.f is None:
        parser.error("--module-runtime при исполнении требует --f")
    if args.module_runtime is not None and args.preprocessor_profile != "standalone":
        parser.error("--module-runtime использует собственный закрытый контекст компиляции")
    if args.file is not None and args.command is not None:
        parser.error("файл и -c нельзя использовать одновременно")
    try:
        database_context = SQLiteDBContext(args.f) if args.f is not None else None
    except BackendError as error:
        print(f"yadinassi: database {error.code}", file=sys.stderr)
        return 1
    application = None
    try:
        if args.module_runtime is not None:
            from .configuration_runtime import ConfigurationApplication
            application = ConfigurationApplication.from_database(database_context)
            interpreter = application.interpreter
        else:
            interpreter = Interpreter(encoding=args.encoding, database_context=database_context,
                                      compilation_profile=args.preprocessor_profile)
    except (BSLError, ValueError, TypeError):
        if database_context is not None:
            database_context.close()
        print("yadinassi: configuration runtime refused", file=sys.stderr)
        return 1
    except BackendError as error:
        if database_context is not None:
            database_context.close()
        print(f"yadinassi: database {error.code}", file=sys.stderr)
        return 1
    try:
        if application is not None and not application.start():
            return 0
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
            if application is not None and not application.close():
                print("yadinassi: application shutdown cancelled", file=sys.stderr)
                return 1
            return result
        interpreter.ensure_complete()
        if application is not None and not application.close():
            print("yadinassi: application shutdown cancelled", file=sys.stderr)
            return 1
    except BSLError as error:
        print(error, file=sys.stderr)
        return 1
    except (OSError, UnicodeError, LookupError, ValueError, TypeError) as error:
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
