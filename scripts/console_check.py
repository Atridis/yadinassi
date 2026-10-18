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
        send(">>> ", "#Region GotoSession\n")
        send("... ", "jump_count = 0;\n")
        send("... ", "~again: jump_count = jump_count + 1;\n")
        send("... ", "If jump_count < 3 Then Goto ~AGAIN; EndIf;\n")
        send("... ", 'Message("goto-count=" + String(jump_count));\n')
        send("... ", "#EndRegion\n")
        expect("goto-count=3")
        send(">>> ", "Goto ~missing;\n")
        expect("Метка не определена")
        send(">>> ", '~recovered: Message("goto-recovered=" + String(jump_count));\n')
        expect("goto-recovered=3")
        send(">>> ", 'целая = цЕл(-12.99); Message("int-value=" + ValueToStringInternal(целая));\n')
        expect('int-value={"N",-12}')
        send(">>> ", 'целая = Int(Undefined);\n')
        send(">>> ", 'Message("int-recovered=" + ValueToStringInternal(целая));\n')
        expect('int-recovered={"N",-12}')
        send(">>> ", 'Message("int-zero=" + ValueToStringInternal(Int(-0.99)));\n')
        expect('int-zero={"N",0}')
        send(">>> ", 'characterText = сИмВоЛ(0) + Char(55357) + Символ(56898);\n')
        send(">>> ", 'characterText = ValueFromStringInternal(\n')
        send("... ", 'ЗначениеВСтрокуВнутр(characterText));\n')
        send(">>> ", 'Message("char-length=" + StrLen(characterText)); '
             'Message("char-nul=" + ValueToStringInternal(CharCode(characterText))); '
             'Message("char-low=" + ValueToStringInternal(КодСимвола(characterText, 3)));\n')
        expect('char-length=3')
        expect('char-nul={"N",0}')
        expect('char-low={"N",56898}')
        send(">>> ", 'Try CharCode("A", Undefined); Except Message("char-caught"); EndTry;\n')
        expect('char-caught')
        send(">>> ", 'characterText = Символ(Undefined);\n')
        send(">>> ", 'Message("char-recovered=" + ValueToStringInternal('
             'CharCode(characterText, 2))); Message("char-alias=" + cHaR(65));\n')
        expect('char-recovered={"N",55357}')
        expect('char-alias=A')
        send(">>> ", 'rounded = оКр(-1.5); Message("round-default=" + ValueToStringInternal(rounded));\n')
        expect('round-default={"N",-2}')
        send(">>> ", 'rounded = Round(1250,\n')
        send("... ", '-2, RoundMode.Round15as10);\n')
        send(">>> ", 'Message("round-mode=" + ValueToStringInternal(rounded));\n')
        expect('round-mode={"N",1200}')
        send(">>> ", 'rounded = Round(1.5, 0, True);\n')
        send(">>> ", 'rounded = Round(Undefined);\n')
        send(">>> ", 'Message("round-recovered=" + ValueToStringInternal(rounded));\n')
        expect('round-recovered={"N",1200}')
        send(">>> ", 'Message("round-exact=" + ValueToStringInternal('
             'Round(Number("123456789012345678901234567890.5"))));\n')
        expect('round-exact={"N",123456789012345678901234567891}')
        send(">>> ", 'mode = ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр('
             'РежимОкругления.Окр15как20));\n')
        send(">>> ", 'Message("round-enum=" + ValueToStringInternal(mode));\n')
        expect('round-enum={"#",32c82ccd-fef3-4070-beb5-b9c52afc781d,1}')
        send(">>> ", 'Message("round-type=" + TypeOf(mode)); '
             'Message("round-restored=" + ValueToStringInternal(Round(-1.5, 0, mode)));\n')
        expect('round-type=РежимОкругления')
        expect('round-restored={"N",-2}')
        send(">>> ", 'seen = New Map; For Each item In RoundMode Do '
             'seen.Insert(item, Round(1.5, 0, item)); EndDo; '
             'Message("enum-count=" + seen.Count()); '
             'Message("enum-ten=" + seen[RoundMode.Round15as10]); '
             'Message("enum-twenty=" + seen[RoundMode.Round15as20]);\n')
        expect('enum-count=2')
        expect('enum-ten=1')
        expect('enum-twenty=2')
        send(">>> ", 'Message("comparison-equal=" + (True = 1)); '
             'Message("comparison-less=" + (0.5 < True));\n')
        expect('comparison-equal=Да')
        expect('comparison-less=Да')
        send(">>> ", 'invalidComparison = True < "1";\n')
        expect('Значения несовместимы для сравнения')
        send(">>> ", 'Message("comparison-recovered=" + (False = 0));\n')
        expect('comparison-recovered=Да')
        send(">>> ", 'extreme = Min(2, True); Message("min-type=" + ValueToStringInternal(extreme));\n')
        expect('min-type={"B",1}')
        send(">>> ", 'extreme = Max(2, "10");\n')
        send(">>> ", 'Message("min-recovered=" + ValueToStringInternal(extreme));\n')
        expect('min-recovered={"B",1}')
        send(">>> ", 'Message("max-tie=" + ValueToStringInternal(Макс(False, 0)));\n')
        expect('max-tie={"B",0}')
        send(">>> ", 'Message("string-max=" + Max("a", "A"));\n')
        expect('string-max=A')
        send(">>> ", 'Message("string-min=" + Min("ё", "е"));\n')
        expect('string-min=е')
        send(">>> ", 'Message("string-order=" + ValueToStringInternal("a" < "A"));\n')
        expect('string-order={"B",1}')
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
        send(">>> ", 'numberValue = nUmBeR("1\u00a0234,5000");\n')
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
        send(">>> ", 'numberValue = Number("12\u00a034,5");\n')
        send(">>> ", 'numberValue\n')
        send(">>> ", 'Number(String(numberValue))\n')
        send(">>> ", 'Message(Number("0.125"));\n')
        send(">>> ", 'StrConcat(StrSplit(numberValue, ","), "|")\n')
        send(">>> ", 'Число("-12\u00a0345\u00a0678,000100")\n')
        send(">>> ", 'exact = Number("123456789012345678901234567890.123456789");\n')
        send(">>> ", 'exact\n')
        send(">>> ", '(Number(String(exact)) = exact)\n')
        send(">>> ", 'String("1234.5000")\n')
        send(">>> ", 'Try\n')
        send("... ", 'Number("1\u202f234,5");\n')
        send("... ", 'Except\n')
        send("... ", 'Message("Группировка перехвачена");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", '"Восстановлено: " + ValueFromStringInternal(ValueToStringInternal(1234.5))\n')
        send(">>> ", '"Тип восстановленного: " + TypeOf(ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(1234.5)))\n')
        send(">>> ", '"Восстановленная структура: " + ValueFromStringInternal(ValueToStringInternal(New Structure("Код", 7))).Код\n')
        send(">>> ", 'ValueToStringInternal(1234.500)\n')
        send(">>> ", 'ЗначениеВСтрокуВнутр(1 / 3)\n')
        send(">>> ", 'quotient = 1 / 7;\n')
        send(">>> ", '"Доля: " + quotient\n')
        send(">>> ", 'part = quotient / (\n')
        send("... ", '3);\n')
        send(">>> ", '"Повторное деление: " + part\n')
        send(">>> ", '"Дробный делитель: " + (1 / 0.3)\n')
        send(">>> ", '"Отрицательное деление: " + (-1 / 6)\n')
        send(">>> ", '"Нормализация: " + (Number("1.0000000000") / 3)\n')
        send(">>> ", '"Тип доли: " + TypeOf(part)\n')
        send(">>> ", '"Точная доля: " + String(part = '
             'Number("0.047619047619047619047619047666666666666666666666666667"))\n')
        send(">>> ", 'Try\n')
        send("... ", 'quotient = -3 / 268435456;\n')
        send("... ", 'Except\n')
        send("... ", 'Message("Половина перехвачена");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'quotient = 1 / 268435456;\n')
        send(">>> ", '"После половины: " + quotient\n')
        send(">>> ", 'quotient = 1 / 0;\n')
        send(">>> ", '"После нуля: " + quotient\n')
        send(">>> ", 'quotient = Number("1e1000000") / 3;\n')
        send(">>> ", '"После предела: " + quotient\n')
        send(">>> ", '"Деление продолжено: " + (1 / 8)\n')
        long_value = '0.' + '3' * 324 + '6'
        long_text = '0,' + '3' * 323 + '4'
        send(">>> ", f'longValue = Number("{long_value}"); negative = -longValue;\n')
        send(">>> ", f'"Длинное представление: " + String(String(negative) = "-{long_text}")\n')
        send(">>> ", '"Длина представления: " + StrLen(String(negative))\n')
        send(">>> ", '"Знак сохранён: " + String(-negative = longValue)\n')
        send(">>> ", f'"Значение сохранено: " + String(longValue = Number("{long_value}"))\n')
        send(">>> ", '"Представление округлено: " + String(Number(String(longValue)) <> longValue)\n')
        send(">>> ", 'presentation = "сохранено";\n')
        for expression, diagnostic, label in (
            ('Number("5e-325")', 'точная половина на границе 324 позиций', 'Половина представления'),
            ('Number("1.' + '3' * 325 + '")', 'при модуле не меньше 1', 'Модуль представления'),
            ('Number("1e4096")', 'превышен предел ресурсов', 'Предел представления'),
        ):
            send(">>> ", f'Try presentation = String({expression}); Except '
                 f'Message("{label}: " + String(Find(ErrorDescription(), "{diagnostic}") > 0)); EndTry;\n')
            send(">>> ", expression + '\n')  # Implicit REPL presentation must also recover.
        send(">>> ", '"Состояние числа: " + String(-negative = longValue)\n')
        send(">>> ", '"После представления: " + presentation\n')
        send(">>> ", 'boundary = StrStartsWith("😀x", Char(55357));\n')
        send(">>> ", 'Message("boundary-prefix=" + ValueToStringInternal(boundary));\n')
        send(">>> ", 'Try\n')
        send("... ", 'СтрЗаканчиваетсяНа("", "");\n')
        send("... ", 'Except\n')
        send("... ", 'Message("boundary-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'boundary = StrStartsWith("a", "");\n')
        send(">>> ", 'Message("boundary-preserved=" + ValueToStringInternal(boundary));\n')
        send(">>> ", 'Message("boundary-suffix=" + ValueToStringInternal(СтрЗаканчиваетсяНа("x😀", Char(56832))));\n')
        send(">>> ", 'rendered = СтрШаблон("%(1)0/%%%1", "x");\n')
        send(">>> ", 'Message("template-result=" + rendered);\n')
        send(">>> ", 'Try\n')
        send("... ", 'StrTemplate("%0");\n')
        send("... ", 'Except\n')
        send("... ", 'Message("template-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'rendered = StrTemplate("%1", 1, 2);\n')
        send(">>> ", 'Message("template-preserved=" + rendered);\n')
        send(">>> ", 'Message("template-recovered=" + StrTemplate("%1", "😀"));\n')
        send(">>> ", 'line = СтрПолучитьСтроку("A" + Char(13) + "Я😀", 2);\n')
        send(">>> ", 'Message("lines-result=" + line);\n')
        send(">>> ", 'Try\n')
        send("... ", 'StrGetLine("A", Undefined);\n')
        send("... ", 'Except\n')
        send("... ", 'Message("lines-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'line = StrGetLine("A", Undefined);\n')
        send(">>> ", 'Message("lines-preserved=" + line);\n')
        send(">>> ", 'Message("lines-count=" + StrLineCount("A" + Char(13) + Char(10) + "B" + Char(10)));\n')
        send(">>> ", 'filled = ЗначениеЗаполнено(False);\n')
        send(">>> ", 'Message("filled-result=" + ValueToStringInternal(filled));\n')
        send(">>> ", 'Try\n')
        send("... ", 'ValueIsFilled(Type("Number"));\n')
        send("... ", 'Except\n')
        send("... ", 'Message("filled-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'filled = ValueIsFilled(Type("Number"));\n')
        send(">>> ", 'Message("filled-preserved=" + ValueToStringInternal(filled));\n')
        send(">>> ", 'Message("filled-empty=" + ValueToStringInternal(ValueIsFilled(New Array)));\n')
        send(">>> ", 'optional = New Array; optional.Добавить(); optional.Insert(0);\n')
        send(">>> ", 'Message("array-default-count=" + optional.Count());\n')
        send(">>> ", 'Try\n')
        send("... ", 'optional.Insert();\n')
        send("... ", 'Except\n')
        send("... ", 'Message("array-default-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'optional[0] = "changed"; optional.Add();\n')
        send(">>> ", 'Message("array-default-write=" + optional[0]);\n')
        send(">>> ", 'Message("array-default-recovered=" + optional.Count());\n')
        send(">>> ", 'gap = New Array; gap.Вставить(3, "tail");\n')
        send(">>> ", 'Message("array-gap-count=" + gap.Count());\n')
        send(">>> ", 'Try\n')
        send("... ", 'gap.Insert(100000000000000000000);\n')
        send("... ", 'Except\n')
        send("... ", 'Message("array-gap-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'gap.Insert(5); Message("array-gap-recovered=" + gap.Count());\n')
        send(">>> ", 'Message("array-gap-undefined=" + ValueToStringInternal(gap[4]));\n')
        send(">>> ", 'Message("occurrence-count=" + СтрЧислоВхождений("aaaa", "aa"));\n')
        send(">>> ", 'Message("template-missing=" + ValueToStringInternal(StrTemplate("%2", "x")));\n')
        send(">>> ", 'Try\n')
        send("... ", 'StrOccurrenceCount("a");\n')
        send("... ", 'Except\n')
        send("... ", 'Message("occurrence-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'Message("occurrence-recovered=" + StrOccurrenceCount("Я😀Я😀", "😀"));\n')
        send(">>> ", 'eval_local = 14; Message("eval-local=" + Eval("eval_local"));\n')
        send(">>> ", 'Try\n')
        send("... ", 'Eval("1 +");\n')
        send("... ", 'Except\n')
        send("... ", 'Message("eval-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'Message("eval-recovered=" + Eval("eval_local + 1"));\n')
        send(">>> ", 'Try\n')
        send("... ", 'StrFind("abc", "b", Undefined);\n')
        send("... ", 'Except\n')
        send("... ", 'Message("strfind-caught");\n')
        send("... ", 'EndTry;\n')
        send(">>> ", 'Message("strfind-recovered=" + СтрНайти("Я😀ёж", "ёж"));\n')
        send(">>> ", "/exit\n")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and read_output():
            pass
        code = process.wait(timeout=2)
        output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data.decode("utf-8"))
        if code != 1 or "Traceback" in output or "^[[D" in output:
            raise AssertionError(f"Console failed ({code}): {output}")
        if (output.count('<консоль>:1:') != 23
                or output.count('ЗначениеЗаполнено для этого типа пока не поддерживается в Yadinassi') != 1
                or output.count('СтрШаблон: очень много параметров') != 1
                or output.count('строка поиска не должна быть пустой') != 1
                or output.count('Метка не определена') != 1
                or output.count('Значения несовместимы для сравнения') != 2
                or output.count('Невозможно преобразовать значение в число') != 5
                or output.count('Окр: ожидается число или значение РежимОкругления') != 1
                or output.count('Тип не поддерживается: Date') != 1
                or output.count('недоступны для записи') != 2
                or output.count('недоступно для записи') != 1
                or output.count('не найдено: Add') != 1
                or output.count('Деление на ноль') != 1
                or output.count('Представление числа: ') != 3
                or output.count('Деление: точная половина на границе округления '
                                'пока не поддерживается в Yadinassi') != 1
                or output.count('Деление: превышен предел ресурсов Yadinassi '
                                '(4096 десятичных разрядов)') != 1):
            raise AssertionError(f"Unexpected console diagnostics: {output}")
        for message, count in (("strfind-caught", 1), ("strfind-recovered=4", 1),
                               ("eval-local=14", 1), ("eval-caught", 1),
                               ("eval-recovered=15", 1), ("occurrence-count=2", 1), ("occurrence-caught", 1),
                               ("occurrence-recovered=2", 1), ('template-missing={"S",""}', 1),
                               ("array-gap-count=4", 1), ("array-gap-caught", 1),
                               ("array-gap-recovered=6", 1), ('array-gap-undefined={"U"}', 1),
                               ("array-default-count=2", 1), ("array-default-caught", 1),
                               ("array-default-write=changed", 1), ("array-default-recovered=3", 1),
                               ("goto-count=3", 1), ("goto-recovered=3", 1),
                               ('filled-result={"B",1}', 1), ('filled-caught', 1),
                               ('filled-preserved={"B",1}', 1), ('filled-empty={"B",0}', 1),
                               ('lines-result=Я😀', 1), ('lines-caught', 1),
                               ('lines-preserved=Я😀', 1), ('lines-count=2', 1),
                               ('template-result=x0/%x', 1), ('template-caught', 1),
                               ('template-preserved=x0/%x', 1), ('template-recovered=😀', 1),
                               ('boundary-prefix={"B",1}', 1), ('boundary-caught', 1),
                               ('boundary-preserved={"B",1}', 1), ('boundary-suffix={"B",1}', 1),
                               ('char-length=3', 1), ('char-nul={"N",0}', 1),
                               ('char-low={"N",56898}', 1), ('char-caught', 1),
                               ('char-recovered={"N",55357}', 1), ('char-alias=A', 1),
                               ("Курсор", 2), ("Вниз", 1), ("Блок", 1),
                               ("Область", 1), ("Вложенная", 1), ("Число", 2),
                               ("типовой ключ", 1), ("Тип", 1), ("Перехвачено", 1),
                               ("Да", 5), ("Нет", 1), ("2", 1),
                               ("ФиксированныйМассив", 1), ("Терминал", 1),
                               ("ФиксированнаяСтруктура", 1), ("фиксированный ключ", 1),
                               ("ФиксированноеСоответствие", 1),
                               ("Фиксированное перехвачено", 1), ("Обход: 2", 1),
                               ("Копия: 5", 1), ("1\u00a0234,5", 4), ("Тип числа: Число", 1),
                               ("Число: 1\u00a0234,5", 1), ("-0,125", 1), ("1\u00a0234.5", 1),
                               ("Число перехвачено", 1), ("0,125", 1), ("1\u00a0234|5", 1),
                               ("-12\u00a0345\u00a0678,0001", 1),
                               ("123\u00a0456\u00a0789\u00a0012\u00a0345\u00a0678"
                                "\u00a0901\u00a0234\u00a0567\u00a0890,123456789", 1),
                               ("1234.5000", 1), ("Группировка перехвачена", 1),
                               ("Доля: 0,142857142857142857142857143", 1),
                               ('Восстановленная структура: 7', 1),
                               ('Восстановлено: 1\u00a0234,5', 1),
                               ('Тип восстановленного: Число', 1),
                               ('{"N",1234.5}', 1),
                               ('{"N",0.333333333333333333333333333}', 1),
                               ("Повторное деление: "
                                "0,047619047619047619047619047666666666666666666666666667", 1),
                               ("Дробный делитель: 3,333333333333333333", 1),
                               ("Отрицательное деление: -0,166666666666666666666666667", 1),
                               ("Нормализация: 0,333333333333333333333333333", 1),
                               ("Тип доли: Число", 1), ("Точная доля: Да", 1),
                               ("Половина перехвачена", 1),
                               ("После половины: 0,142857142857142857142857143", 1),
                               ("После нуля: 0,142857142857142857142857143", 1),
                               ("После предела: 0,142857142857142857142857143", 1),
                               ("Деление продолжено: 0,125", 1),
                               ("Длинное представление: Да", 1), ("Длина представления: 327", 1),
                               ("Знак сохранён: Да", 1), ("Значение сохранено: Да", 1),
                               ("Представление округлено: Да", 1), ("Половина представления: Да", 1),
                               ("Модуль представления: Да", 1), ("Предел представления: Да", 1),
                               ("Состояние числа: Да", 1), ("После представления: сохранено", 1)):
            if output.count(f"\r\n{message}\r\n") != count:
                raise AssertionError(f"Unexpected console output for {message!r}: {output}")
        return output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
