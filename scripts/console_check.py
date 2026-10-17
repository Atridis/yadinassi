"""POSIX terminal regression check shared by source and frozen binary tests."""

import os
import re
import subprocess
import time


def check_console(command: list[str], *, cwd, env=None) -> str:
    # Imports stay local so the build scripts can also be used on Windows.
    import errno
    import fcntl
    import pty
    import select
    import struct
    import termios

    master, slave = pty.openpty()
    attributes = termios.tcgetattr(slave)
    attributes[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attributes)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
    terminal_env = dict(os.environ if env is None else env)
    terminal_env["TERM"] = "xterm"
    terminal_env["PROMPT_TOOLKIT_NO_CPR"] = "1"
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                               cwd=cwd, env=terminal_env)
    os.close(slave)
    data = bytearray()
    position = 0

    def read_output() -> bool:
        if not select.select([master], [], [], 0.1)[0]:
            return process.poll() is None
        try:
            chunk = os.read(master, 65536)
        except OSError as error:
            if error.errno == errno.EIO:
                return False
            raise
        data.extend(chunk)
        return bool(chunk)

    def expect(text: str) -> None:
        nonlocal position
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            found = data.find(text.encode(), position)
            if found >= 0:
                position = found + len(text)
                return
            if not read_output():
                break
        raise AssertionError(f"Console did not show {text!r}: {data.decode('utf-8', errors='replace')}")

    def send(prompt: str, keys: str, *, forbidden_lines: tuple[str, ...] = ()) -> None:
        # The renderer can replace trailing spaces with cursor movement.
        expect(prompt.rstrip())
        if forbidden_lines:
            output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data.decode("utf-8"))
            for line in forbidden_lines:
                if f"\r\n{line}\r\n" in output:
                    raise AssertionError(f"Console executed an unfinished region: {output}")
        os.write(master, keys.encode("utf-8"))
        # Each completed prompt disables bracketed paste; redraws do not.
        expect("\x1b[?2004l")

    def corrected_line(message: str) -> str:
        text = f'Соообщить("{message}");'
        # Move to the extra Cyrillic letter, step right, then delete it.
        return text + "\x1b[D" * (len(text) - 2) + "\x1b[C\x7f\n"

    try:
        send(">>> ", corrected_line("Курсор"))
        send(">>> ", "\x1b[A\n")  # Recall and execute the corrected line.
        send(">>> ", '\x1b[A\x1b[BСообщить("Вниз");\n')
        send(">>> ", "Если Истина Тогда\n")
        send("... ", corrected_line("Блок"))
        send("... ", "КонецЕсли;\n")
        send(">>> ", "#Область Внешняя\n")
        send("... ", 'Сообщить("Область");\n')
        region_output = ("Область", "Вложенная")
        send("... ", "#Region Inner\n", forbidden_lines=region_output)
        send("... ", 'Сообщить("Вложенная");\n', forbidden_lines=region_output)
        send("... ", "#EndRegion\n", forbidden_lines=region_output)
        send("... ", "#КонецОбласти\n", forbidden_lines=region_output)
        send(">>> ", 'kind = Тип("ЧиСлО");\n')
        send(">>> ", 'kind\n')
        send(">>> ", 'm = New Map; m[kind] = "типовой ключ";\n')
        send(">>> ", 'm[TypeOf(1)]\n')
        send(">>> ", 'ТипЗнч(\n')
        send("... ", 'kind)\n')
        send(">>> ", 'Try\n')
        send("... ", 'TypeOf(Message);\n')
        send("... ", 'Except\n')
        send("... ", 'Message("Перехвачено");\n')
        send("... ", 'EndTry;\n')
        # An uncaught failure must preserve the value and restore the main prompt.
        send(">>> ", 'kind = Type("Date");\n')
        send(">>> ", 'kind\n')
        send(">>> ", '(TypeOf(True) = Type("bOoLeAn"))\n')
        send(">>> ", '(kind = "Число")\n')
        send(">>> ", 'frozen = New FixedArray(\n')
        send("... ", 'New Array(2));\n')
        send(">>> ", 'frozen.Count()\n')
        send(">>> ", 'TypeOf(frozen)\n')
        send(">>> ", 'frozen[0] = 12;\n')
        send(">>> ", '(frozen[0] = Undefined)\n')
        send(">>> ", 'record = Новый ФиксированнаяСтруктура(\n')
        send("... ", '"Name,Count", "Терминал", 7);\n')
        send(">>> ", 'record.Name = "изменено";\n')
        send(">>> ", 'Var value; record.Property("NAME", value);\n')
        send(">>> ", 'value\n')
        send(">>> ", 'TypeOf(record)\n')
        send(">>> ", 'mutable = New Map; mutable["key"] = "фиксированный ключ";\n')
        send(">>> ", 'lookup = New FixedMap(mutable); mutable["key"] = "изменено";\n')
        send(">>> ", 'lookup["key"] = "изменено";\n')
        send(">>> ", 'lookup["key"]\n')
        send(">>> ", 'TypeOf(lookup)\n')
        send(">>> ", 'frozen.Add(99);\n')
        send(">>> ", 'Try\n')
        send("... ", 'record.Clear();\n')
        send("... ", 'Except\n')
        send("... ", 'Message("Фиксированное перехвачено");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'visited = 0;\n')
        send(">>> ", 'For Each item In frozen Do\n')
        send("... ", 'visited = visited + 1;\n')
        send("... ", 'EndDo;\n')
        send(">>> ", 'Message("Обход: " + String(visited));\n')
        send(">>> ", 'copy = New Array(frozen); copy[0] = 5;\n')
        send(">>> ", 'Message("Копия: " + String(copy[0]));\n')
        send(">>> ", '(frozen[0] = Undefined)\n')
        send(">>> ", 'numberValue = nUmBeR("12.5000");\n')
        send(">>> ", 'numberValue\n')
        send(">>> ", 'сТрОкА(numberValue)\n')
        send(">>> ", '"Тип числа: " + TypeOf(numberValue)\n')
        send(">>> ", '"Число: " + numberValue\n')
        send(">>> ", 'Число(\n')
        send("... ", '"-0,12500")\n')
        send(">>> ", 'StrReplace(numberValue, ",", ".")\n')
        send(">>> ", 'Try\n')
        send("... ", 'Number("1,,2");\n')
        send("... ", 'Except\n')
        send("... ", 'Message("Число перехвачено");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'numberValue = Number("1,2.3");\n')
        send(">>> ", 'numberValue\n')
        send(">>> ", 'Number(String(numberValue))\n')
        send(">>> ", 'Message(Number("0.125"));\n')
        send(">>> ", 'StrConcat(StrSplit(numberValue, ","), "|")\n')
        send(">>> ", "/exit\n")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and read_output():
            pass
        code = process.wait(timeout=2)
        output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data.decode("utf-8"))
        if code != 1 or "Traceback" in output or "^[[D" in output:
            raise AssertionError(f"Console failed ({code}): {output}")
        if (output.count('<консоль>:1:') != 6
                or output.count('Тип не поддерживается: Date') != 1
                or output.count('недоступны для записи') != 2
                or output.count('недоступно для записи') != 1
                or output.count('не найдено: Add') != 1
                or output.count('Невозможно преобразовать значение в число') != 1):
            raise AssertionError(f"Unexpected console diagnostics: {output}")
        for message, count in (("Курсор", 2), ("Вниз", 1), ("Блок", 1),
                               ("Область", 1), ("Вложенная", 1), ("Число", 2),
                               ("типовой ключ", 1), ("Тип", 1), ("Перехвачено", 1),
                               ("Да", 4), ("Нет", 1), ("2", 1),
                               ("ФиксированныйМассив", 1), ("Терминал", 1),
                               ("ФиксированнаяСтруктура", 1), ("фиксированный ключ", 1),
                               ("ФиксированноеСоответствие", 1),
                               ("Фиксированное перехвачено", 1), ("Обход: 2", 1),
                               ("Копия: 5", 1), ("12,5", 4), ("Тип числа: Число", 1),
                               ("Число: 12,5", 1), ("-0,125", 1), ("12.5", 1),
                               ("Число перехвачено", 1), ("0,125", 1), ("12|5", 1)):
            if output.count(f"\r\n{message}\r\n") != count:
                raise AssertionError(f"Unexpected console output for {message!r}: {output}")
        return output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
