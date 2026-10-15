"""Test the distributed executable outside the source tree and without PYTHONPATH."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # Redirected Windows output can default to cp1252, which cannot encode BSL text.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    executable = str(Path(sys.argv[1]).resolve())
    expected = (ROOT / "tests" / "fixtures" / "basic.out").read_text(encoding="utf-8")
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    env["PYTHONIOENCODING"] = "utf-8"
    # The bundled interpreter must work without finding Python on PATH.
    env["PATH"] = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32" if os.name == "nt" else "/usr/bin:/bin"
    with tempfile.TemporaryDirectory(prefix="yadinassi-smoke-") as temporary:
        sample = Path(temporary) / "пример.bsl"
        sample.write_bytes((ROOT / "code_samples" / "basic.bsl").read_bytes())
        module = Path(temporary) / "Побочное.bsl"
        module.write_text('Функция ПолучитьСумму(А, Б = 2) Экспорт\n'
                          'Возврат А + Б;\nКонецФункции\n', encoding="utf-8-sig")
        importer = Path(temporary) / "Основное.bsl"
        importer.write_text('# Импорт Побочное.bsl\n'
                            'Сообщить(Побочное.ПолучитьСумму(1));', encoding="utf-8")
        project = Path(temporary) / "project"
        nested = project / "Справочник"
        deeper = nested / "Вложенное"
        deeper.mkdir(parents=True)
        (nested / module.name).write_bytes(module.read_bytes())
        (deeper / "Другое.bsl").write_text(
            'Функция Ответ() Экспорт Возврат "вложенный"; КонецФункции',
            encoding="utf-8-sig")
        nested_importer = project / "Основное.bsl"
        nested_importer.write_text(
            '# Импорт Справочник.Побочное.bsl\n'
            '# Импорт Справочник.Вложенное.Другое.bsl\n'
            'Сообщить(справочник.ПОБОЧНОЕ.получитьсумму(1, 2));\n'
            'Сообщить(СПРАВОЧНИК.вложенное.ДРУГОЕ.ответ());', encoding="utf-8-sig")
        cases = [
            ([str(importer)], None, "3\n", 0),
            ([str(nested_importer)], None, "3\nвложенный\n", 0),
            ([str(Path("project") / nested_importer.name)], None, "3\nвложенный\n", 0),
            ([str(sample)], None, expected, 0),
            (["-c", 'Сообщить("Привет")'], None, "Привет\n", 0),
            (["-с", 'Сообщить("Кириллица")'], None, "Кириллица\n", 0),
            ([], 'х = 40;\nЕсли Истина Тогда\nх = х + 2;\nКонецЕсли;\nСообщить(х);\n/exit\n', "42\n", 0),
            (["-"], 'Сообщить("stdin")', "stdin\n", 0),
            (["-c", "Сообщить(1 / 0)"], None, "", 1),
        ]
        for arguments, stdin, stdout, code in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding="utf-8", cwd=temporary, env=env, timeout=30)
            if result.returncode != code or result.stdout != stdout:
                raise AssertionError(f"Failed {arguments!r}: {result!r}")
            if code == 0 and result.stderr:
                raise AssertionError(result.stderr)
            if code and ("Деление на ноль" not in result.stderr or "Traceback" in result.stderr):
                raise AssertionError(result.stderr)
        if os.name != "nt":
            from console_check import check_console

            check_console([executable], cwd=temporary, env=env)
            print("Binary terminal tests passed: cursor editing, history, multiline input")
    print("Binary smoke tests passed: file, sibling/nested imports, -c, -с, console, stdin, errors")


if __name__ == "__main__":
    main()
