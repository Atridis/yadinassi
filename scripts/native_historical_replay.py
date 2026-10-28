"""Source-bound complete Windows replay; live CI runs full current source."""
import hashlib

# Windows capture 4a3f55f8 predates the final cache and field-reference probes.
# Keep its entire source and output coverage; never truncate observed output.
HISTORICAL_COLLECTIONS_BLOB = "137dca5e4b6a47ea083a0dfe989e07c22d91a9e6"
HISTORICAL_COLLECTIONS_OUTPUT_BLOB = "97e90791a4011bd7f6ef2922533f92f698557cbd"
FINAL_PROBE_BLOCKS = (
    ("// Начало заключительных проб пустой строки кэша списка.\n",
     "// Конец заключительных проб пустой строки кэша списка.\n\n"),
    ("// Начало заключительных наблюдений пустой строки кэша списка.\n",
     "// Конец заключительных наблюдений пустой строки кэша списка.\n"),
)


FIELD_REFERENCE_BLOCKS = (
    ("// Begin ValueList field reference helpers.\n",
     "// End ValueList field reference helpers.\n\n"),
    ("// Begin ValueList field reference observations.\n",
     "// End ValueList field reference observations.\n"),
)


def without_field_reference_probes(text):
    """Remove only the pending additions; callers retain historical hash binding."""
    for start, end in FIELD_REFERENCE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("field reference probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


FILL_EXCLUDE_ORDER_PROBE_BLOCKS = (
    ('// Begin FillPropertyValues EXCLUDE source-order discriminator helpers.\n',
     '// End FillPropertyValues EXCLUDE source-order discriminator helpers.\n\n'),
    ('// Begin FillPropertyValues EXCLUDE source-order discriminator observations.\n',
     '// End FillPropertyValues EXCLUDE source-order discriminator observations.\n'),
)


TREE_LOAD_HELPERS_START = '// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\n'
TREE_LOAD_HELPERS_END = '// End bounded ValueTree LoadColumn helpers.\n\n'
TREE_LOAD_CALLS_START = '// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\n'
TREE_LOAD_CALLS_END = '// End bounded ValueTree LoadColumn observations.\n'


TREE_LOAD_CALIBRATION_SOURCE_SHA256 = '73ffd118fa061e7ecbdfafc8701de03c887e24020fc2fec7d30a04030a2cf03b'
TREE_LOAD_ORIGINAL_SOURCE_SHA256 = '0f36f76a44f63f9623a3c204c5cace3dd4d4328b4465f3bb002f660fc96e684b'
TREE_LOAD_CALIBRATION_EDITS = (('Процедура TreeLoadCalibrate()\n    X = Новый Структура("Mark", "base"); Y = Новый Структура("Mark", "base"); Alias = X;\n    Если X <> Alias Или X = Y Тогда ВызватьИсключение "tree-load-structure-identity"; КонецЕсли;\n    A = TreeLoadPair(1, Истина); B = TreeLoadPair(1, Истина); Alias = A;\n    Если A <> Alias Или A = B Тогда ВызватьИсключение "tree-load-array-identity"; КонецЕсли;\n    F = Новый ФиксированныйМассив(A); G = Новый ФиксированныйМассив(A); Alias = F;\n    Если F <> Alias Или F = G Тогда ВызватьИсключение "tree-load-fixed-identity"; КонецЕсли;\n    T = Новый ДеревоЗначений; Other = Новый ДеревоЗначений;\n    RootRows = T.Rows; Cols = T.Columns; R = T.Rows.Add(); OtherRow = T.Rows.Add(); ChildRows = R.Rows;\n    Если T.Rows <> RootRows Или T.Columns <> Cols Или R.Rows <> ChildRows\n        Или RootRows = Other.Rows Или Cols = Other.Columns Или ChildRows = OtherRow.Rows Тогда\n        ВызватьИсключение "tree-load-container-identity";\n    КонецЕсли;\n    Если R <> T.Rows.Get(0) Или R = OtherRow Тогда ВызватьИсключение "tree-load-row-identity"; КонецЕсли;\n    Refs = Новый Массив;\n    Если Не TreeLoadExact(TreeLoadCell(1, Refs), "1_") Или Не TreeLoadExact(TreeLoadCell(Истина, Refs), "T_")\n        Или Не TreeLoadExact(TreeLoadCell("1", Refs), "j_") Тогда ВызватьИсключение "tree-load-scalar-calibration"; КонецЕсли;\nКонецПроцедуры', 'Функция TreeLoadCalibrate()\n    Stage = "0";\n    Попытка\n        Stage = "1";\n        X = Новый Структура("Mark", "base"); Y = Новый Структура("Mark", "base"); Alias = X;\n        Stage = "2";\n        Если X <> Alias Тогда ВызватьИсключение "tree-load-structure-alias"; КонецЕсли;\n        Stage = "3";\n        Если X = Y Тогда ВызватьИсключение "tree-load-structure-distinct"; КонецЕсли;\n        Stage = "4";\n        A = TreeLoadPair(1, Истина); B = TreeLoadPair(1, Истина); Alias = A;\n        Stage = "5";\n        Если A <> Alias Тогда ВызватьИсключение "tree-load-array-alias"; КонецЕсли;\n        Stage = "6";\n        Если A = B Тогда ВызватьИсключение "tree-load-array-distinct"; КонецЕсли;\n        Stage = "7";\n        F = Новый ФиксированныйМассив(A); G = Новый ФиксированныйМассив(A); Alias = F;\n        Stage = "8";\n        Если F <> Alias Тогда ВызватьИсключение "tree-load-fixed-alias"; КонецЕсли;\n        Stage = "9";\n        Если F = G Тогда ВызватьИсключение "tree-load-fixed-distinct"; КонецЕсли;\n        Stage = "A";\n        T = Новый ДеревоЗначений; Other = Новый ДеревоЗначений;\n        Stage = "B";\n        RootRows = T.Rows;\n        Stage = "C";\n        Cols = T.Columns;\n        Stage = "D";\n        R = T.Rows.Add();\n        Stage = "E";\n        OtherRow = T.Rows.Add();\n        Stage = "F";\n        ChildRows = R.Rows;\n        Stage = "G";\n        Если T.Rows <> RootRows Тогда ВызватьИсключение "tree-load-root-alias"; КонецЕсли;\n        Stage = "H";\n        Если T.Columns <> Cols Тогда ВызватьИсключение "tree-load-columns-alias"; КонецЕсли;\n        Stage = "I";\n        Если R.Rows <> ChildRows Тогда ВызватьИсключение "tree-load-child-alias"; КонецЕсли;\n        Stage = "J";\n        Если RootRows = Other.Rows Тогда ВызватьИсключение "tree-load-root-distinct"; КонецЕсли;\n        Stage = "K";\n        Если Cols = Other.Columns Тогда ВызватьИсключение "tree-load-columns-distinct"; КонецЕсли;\n        Stage = "L";\n        Если ChildRows = OtherRow.Rows Тогда ВызватьИсключение "tree-load-child-distinct"; КонецЕсли;\n        Stage = "M";\n        Если R <> T.Rows.Get(0) Тогда ВызватьИсключение "tree-load-row-alias"; КонецЕсли;\n        Stage = "N";\n        Если R = OtherRow Тогда ВызватьИсключение "tree-load-row-distinct"; КонецЕсли;\n        Stage = "O";\n        Refs = Новый Массив;\n        Stage = "P";\n        Если Не TreeLoadExact(TreeLoadCell(1, Refs), "1_") Тогда ВызватьИсключение "tree-load-number-calibration"; КонецЕсли;\n        Stage = "Q";\n        Если Не TreeLoadExact(TreeLoadCell(Истина, Refs), "T_") Тогда ВызватьИсключение "tree-load-bool-calibration"; КонецЕсли;\n        Stage = "R";\n        Если Не TreeLoadExact(TreeLoadCell("1", Refs), "j_") Тогда ВызватьИсключение "tree-load-string-calibration"; КонецЕсли;\n    Исключение\n        Возврат Stage;\n    КонецПопытки;\n    Возврат "-";\nКонецФункции'), ('    Попытка TreeLoadCalibrate(); Исключение Возврат "1?C0--" + Failed; КонецПопытки;', '    Calibration = TreeLoadCalibrate();\n    Если Calibration <> "-" Тогда Возврат "1?C0" + Calibration + "-" + Failed; КонецЕсли;'))


TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256 = '6f42aab85ab386915e708b07bcb56cb2bbad58469dd1b08b0364f9541c7e83f6'
TREE_ROWS_DIAGNOSTIC_EDITS = (('// End bounded ValueTree UnloadColumn helpers.\n\n// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\nФункция TreeLoadExact(Знач Left, Знач Right)\n', '// End bounded ValueTree UnloadColumn helpers.\n\n// Begin isolated Rows view diagnostic (fail-only; no LoadColumn calls).\nФункция TreeRowsDiagnosticPart(Знач Part)\n    Попытка\n        Если Part = 1 Или Part = 2 Тогда\n            // Preserve original calibration A-F ordering, including retention before Add.\n            T = Новый ДеревоЗначений; Other = Новый ДеревоЗначений;\n            Saved = T.Rows; Cols = T.Columns;\n            R = T.Rows.Add(); OtherRow = T.Rows.Add(); ChildRows = R.Rows;\n            Alias = Saved;\n        ИначеЕсли Part = 3 Или Part = 4 Тогда\n            T = Новый ДеревоЗначений; T.Columns.Add("Marker"); Saved = T.Rows;\n            Если Saved.Count() <> 0 Или T.Rows.Count() <> 0 Тогда Возврат "?"; КонецЕсли;\n        Иначе\n            Возврат "?";\n        КонецЕсли;\n    Исключение\n        Возврат "?";\n    КонецПопытки;\n    Попытка\n        Если Part = 1 Тогда\n            Result = T.Rows <> Saved;\n        ИначеЕсли Part = 2 Тогда\n            Result = Alias <> Saved;\n        ИначеЕсли Part = 3 Тогда\n            Added = Saved.Add(); Added.Marker = 17; View = T.Rows;\n            Result = View.Count() = 1;\n            Если Result Тогда Result = ТипЗнч(View.Get(0).Marker) = Тип("Число"); КонецЕсли;\n            Если Result Тогда Result = View.Get(0).Marker = 17; КонецЕсли;\n        Иначе\n            Added = T.Rows.Add(); Added.Marker = 17; View = Saved;\n            Result = View.Count() = 1;\n            Если Result Тогда Result = ТипЗнч(View.Get(0).Marker) = Тип("Число"); КонецЕсли;\n            Если Result Тогда Result = View.Get(0).Marker = 17; КонецЕсли;\n        КонецЕсли;\n        Если Result Тогда Возврат "T"; КонецЕсли;\n        Возврат "F";\n    Исключение\n        Возврат "E";\n    КонецПопытки;\nКонецФункции\n\nФункция TreeRowsDiagnosticExperiment()\n    Result = "";\n    Для Part = 1 По 4 Цикл\n        Trit = TreeRowsDiagnosticPart(Part);\n        Если Trit = "?" Тогда Возврат "?"; КонецЕсли;\n        Result = Result + Trit;\n    КонецЦикла;\n    Возврат Result;\nКонецФункции\n\nФункция TreeRowsDiagnosticProbe(Знач Case, Знач Diagnostic)\n    Failed = "1?O0--!..........................................................";\n    Если ТипЗнч(Case) <> Тип("Число") Тогда Возврат Failed; КонецЕсли;\n    Если Case < 1 Или Case > 45 Или Цел(Case) <> Case Тогда Возврат Failed; КонецЕсли;\n    Если ТипЗнч(Diagnostic) <> Тип("Строка") Тогда Возврат Failed; КонецЕсли;\n    Если СтрДлина(Diagnostic) <> 4 Тогда Возврат Failed; КонецЕсли;\n    Для P = 1 По 4 Цикл\n        Code = КодСимвола(Diagnostic, P);\n        Если Code <> 84 И Code <> 70 И Code <> 69 Тогда Возврат Failed; КонецЕсли;\n    КонецЦикла;\n    Возврат "1?D0" + Diagnostic + "!........................................................";\nКонецФункции\n// End isolated Rows view diagnostic.\n\n// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\nФункция TreeLoadExact(Знач Left, Знач Right)\n'), ('// End bounded ValueTree UnloadColumn observations.\n// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\nПоказать("TL01", TreeLoadProbe(1));\nПоказать("TL02", TreeLoadProbe(2));\nПоказать("TL03", TreeLoadProbe(3));\nПоказать("TL04", TreeLoadProbe(4));\nПоказать("TL05", TreeLoadProbe(5));\nПоказать("TL06", TreeLoadProbe(6));\nПоказать("TL07", TreeLoadProbe(7));\nПоказать("TL08", TreeLoadProbe(8));\nПоказать("TL09", TreeLoadProbe(9));\nПоказать("TL10", TreeLoadProbe(10));\nПоказать("TL11", TreeLoadProbe(11));\nПоказать("TL12", TreeLoadProbe(12));\nПоказать("TL13", TreeLoadProbe(13));\nПоказать("TL14", TreeLoadProbe(14));\nПоказать("TL15", TreeLoadProbe(15));\nПоказать("TL16", TreeLoadProbe(16));\nПоказать("TL17", TreeLoadProbe(17));\nПоказать("TL18", TreeLoadProbe(18));\nПоказать("TL19", TreeLoadProbe(19));\nПоказать("TL20", TreeLoadProbe(20));\nПоказать("TL21", TreeLoadProbe(21));\nПоказать("TL22", TreeLoadProbe(22));\nПоказать("TL23", TreeLoadProbe(23));\nПоказать("TL24", TreeLoadProbe(24));\nПоказать("TL25", TreeLoadProbe(25));\nПоказать("TL26", TreeLoadProbe(26));\nПоказать("TL27", TreeLoadProbe(27));\nПоказать("TL28", TreeLoadProbe(28));\nПоказать("TL29", TreeLoadProbe(29));\nПоказать("TL30", TreeLoadProbe(30));\nПоказать("TL31", TreeLoadProbe(31));\nПоказать("TL32", TreeLoadProbe(32));\nПоказать("TL33", TreeLoadProbe(33));\nПоказать("TL34", TreeLoadProbe(34));\nПоказать("TL35", TreeLoadProbe(35));\nПоказать("TL36", TreeLoadProbe(36));\nПоказать("TL37", TreeLoadProbe(37));\nПоказать("TL38", TreeLoadProbe(38));\nПоказать("TL39", TreeLoadProbe(39));\nПоказать("TL40", TreeLoadProbe(40));\nПоказать("TL41", TreeLoadProbe(41));\nПоказать("TL42", TreeLoadProbe(42));\nПоказать("TL43", TreeLoadProbe(43));\nПоказать("TL44", TreeLoadProbe(44));\nПоказать("TL45", TreeLoadProbe(45));\n// End bounded ValueTree LoadColumn observations.\n', '// End bounded ValueTree UnloadColumn observations.\n// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\nTreeRowsDiagnostic = TreeRowsDiagnosticExperiment();\nПоказать("TL01", TreeRowsDiagnosticProbe(1, TreeRowsDiagnostic));\nПоказать("TL02", TreeRowsDiagnosticProbe(2, TreeRowsDiagnostic));\nПоказать("TL03", TreeRowsDiagnosticProbe(3, TreeRowsDiagnostic));\nПоказать("TL04", TreeRowsDiagnosticProbe(4, TreeRowsDiagnostic));\nПоказать("TL05", TreeRowsDiagnosticProbe(5, TreeRowsDiagnostic));\nПоказать("TL06", TreeRowsDiagnosticProbe(6, TreeRowsDiagnostic));\nПоказать("TL07", TreeRowsDiagnosticProbe(7, TreeRowsDiagnostic));\nПоказать("TL08", TreeRowsDiagnosticProbe(8, TreeRowsDiagnostic));\nПоказать("TL09", TreeRowsDiagnosticProbe(9, TreeRowsDiagnostic));\nПоказать("TL10", TreeRowsDiagnosticProbe(10, TreeRowsDiagnostic));\nПоказать("TL11", TreeRowsDiagnosticProbe(11, TreeRowsDiagnostic));\nПоказать("TL12", TreeRowsDiagnosticProbe(12, TreeRowsDiagnostic));\nПоказать("TL13", TreeRowsDiagnosticProbe(13, TreeRowsDiagnostic));\nПоказать("TL14", TreeRowsDiagnosticProbe(14, TreeRowsDiagnostic));\nПоказать("TL15", TreeRowsDiagnosticProbe(15, TreeRowsDiagnostic));\nПоказать("TL16", TreeRowsDiagnosticProbe(16, TreeRowsDiagnostic));\nПоказать("TL17", TreeRowsDiagnosticProbe(17, TreeRowsDiagnostic));\nПоказать("TL18", TreeRowsDiagnosticProbe(18, TreeRowsDiagnostic));\nПоказать("TL19", TreeRowsDiagnosticProbe(19, TreeRowsDiagnostic));\nПоказать("TL20", TreeRowsDiagnosticProbe(20, TreeRowsDiagnostic));\nПоказать("TL21", TreeRowsDiagnosticProbe(21, TreeRowsDiagnostic));\nПоказать("TL22", TreeRowsDiagnosticProbe(22, TreeRowsDiagnostic));\nПоказать("TL23", TreeRowsDiagnosticProbe(23, TreeRowsDiagnostic));\nПоказать("TL24", TreeRowsDiagnosticProbe(24, TreeRowsDiagnostic));\nПоказать("TL25", TreeRowsDiagnosticProbe(25, TreeRowsDiagnostic));\nПоказать("TL26", TreeRowsDiagnosticProbe(26, TreeRowsDiagnostic));\nПоказать("TL27", TreeRowsDiagnosticProbe(27, TreeRowsDiagnostic));\nПоказать("TL28", TreeRowsDiagnosticProbe(28, TreeRowsDiagnostic));\nПоказать("TL29", TreeRowsDiagnosticProbe(29, TreeRowsDiagnostic));\nПоказать("TL30", TreeRowsDiagnosticProbe(30, TreeRowsDiagnostic));\nПоказать("TL31", TreeRowsDiagnosticProbe(31, TreeRowsDiagnostic));\nПоказать("TL32", TreeRowsDiagnosticProbe(32, TreeRowsDiagnostic));\nПоказать("TL33", TreeRowsDiagnosticProbe(33, TreeRowsDiagnostic));\nПоказать("TL34", TreeRowsDiagnosticProbe(34, TreeRowsDiagnostic));\nПоказать("TL35", TreeRowsDiagnosticProbe(35, TreeRowsDiagnostic));\nПоказать("TL36", TreeRowsDiagnosticProbe(36, TreeRowsDiagnostic));\nПоказать("TL37", TreeRowsDiagnosticProbe(37, TreeRowsDiagnostic));\nПоказать("TL38", TreeRowsDiagnosticProbe(38, TreeRowsDiagnostic));\nПоказать("TL39", TreeRowsDiagnosticProbe(39, TreeRowsDiagnostic));\nПоказать("TL40", TreeRowsDiagnosticProbe(40, TreeRowsDiagnostic));\nПоказать("TL41", TreeRowsDiagnosticProbe(41, TreeRowsDiagnostic));\nПоказать("TL42", TreeRowsDiagnosticProbe(42, TreeRowsDiagnostic));\nПоказать("TL43", TreeRowsDiagnosticProbe(43, TreeRowsDiagnostic));\nПоказать("TL44", TreeRowsDiagnosticProbe(44, TreeRowsDiagnostic));\nПоказать("TL45", TreeRowsDiagnosticProbe(45, TreeRowsDiagnostic));\n// End bounded ValueTree LoadColumn observations.\n'))


TREE_COLUMNS_DIAGNOSTIC_SOURCE_SHA256 = '092338cab2793224ced334ee721f243136113c2dbd2cf9d569aea67a66b533e0'
TREE_COLUMNS_DIAGNOSTIC_EDITS = (('// End bounded ValueTree UnloadColumn helpers.\n\n// Begin isolated Rows view diagnostic (fail-only; no LoadColumn calls).\nФункция TreeRowsDiagnosticPart(Знач Part)\n    Попытка\n        Если Part = 1 Или Part = 2 Тогда\n            // Preserve original calibration A-F ordering, including retention before Add.\n            T = Новый ДеревоЗначений; Other = Новый ДеревоЗначений;\n            Saved = T.Rows; Cols = T.Columns;\n            R = T.Rows.Add(); OtherRow = T.Rows.Add(); ChildRows = R.Rows;\n            Alias = Saved;\n        ИначеЕсли Part = 3 Или Part = 4 Тогда\n            T = Новый ДеревоЗначений; T.Columns.Add("Marker"); Saved = T.Rows;\n            Если Saved.Count() <> 0 Или T.Rows.Count() <> 0 Тогда Возврат "?"; КонецЕсли;\n        Иначе\n            Возврат "?";\n', '// End bounded ValueTree UnloadColumn helpers.\n\n// Begin isolated Columns view diagnostic (fail-only; no LoadColumn calls).\nФункция TreeColumnsDiagnosticPart(Знач Part)\n    Попытка\n        Если Part = 1 Или Part = 2 Тогда\n            // Preserve original calibration A-F ordering, including retention before Add.\n            T = Новый ДеревоЗначений; Other = Новый ДеревоЗначений;\n            RootRows = T.Rows; Saved = T.Columns;\n            R = T.Rows.Add(); OtherRow = T.Rows.Add(); ChildRows = R.Rows;\n            Alias = Saved;\n        ИначеЕсли Part = 3 Или Part = 4 Тогда\n            T = Новый ДеревоЗначений; Saved = T.Columns;\n            Если Saved.Count() <> 0 Или T.Columns.Count() <> 0 Тогда Возврат "?"; КонецЕсли;\n        Иначе\n            Возврат "?";\n'), ('    Попытка\n        Если Part = 1 Тогда\n            Result = T.Rows <> Saved;\n        ИначеЕсли Part = 2 Тогда\n            Result = Alias <> Saved;\n        ИначеЕсли Part = 3 Тогда\n            Added = Saved.Add(); Added.Marker = 17; View = T.Rows;\n            Result = View.Count() = 1;\n            Если Result Тогда Result = ТипЗнч(View.Get(0).Marker) = Тип("Число"); КонецЕсли;\n            Если Result Тогда Result = View.Get(0).Marker = 17; КонецЕсли;\n        Иначе\n            Added = T.Rows.Add(); Added.Marker = 17; View = Saved;\n            Result = View.Count() = 1;\n            Если Result Тогда Result = ТипЗнч(View.Get(0).Marker) = Тип("Число"); КонецЕсли;\n            Если Result Тогда Result = View.Get(0).Marker = 17; КонецЕсли;\n        КонецЕсли;\n        Если Result Тогда Возврат "T"; КонецЕсли;\n', '    Попытка\n        Если Part = 1 Тогда\n            Result = T.Columns <> Saved;\n        ИначеЕсли Part = 2 Тогда\n            Result = Alias <> Saved;\n        ИначеЕсли Part = 3 Тогда\n            Added = Saved.Add("Marker"); Added.Width = 17; View = T.Columns;\n            Result = View.Count() = 1;\n            Если Result Тогда Name = View.Get(0).Name; Result = ТипЗнч(Name) = Тип("Строка"); КонецЕсли;\n            Если Result Тогда Result = СтрДлина(Name) = 6; КонецЕсли;\n            Если Result Тогда\n                Result = КодСимвола(Name, 1) = 77 И КодСимвола(Name, 2) = 97 И КодСимвола(Name, 3) = 114\n                    И КодСимвола(Name, 4) = 107 И КодСимвола(Name, 5) = 101 И КодСимвола(Name, 6) = 114;\n            КонецЕсли;\n            Если Result Тогда Result = ТипЗнч(View.Get(0).Width) = Тип("Число"); КонецЕсли;\n            Если Result Тогда Result = View.Get(0).Width = 17; КонецЕсли;\n        Иначе\n            Added = T.Columns.Add("Marker"); Added.Width = 17; View = Saved;\n            Result = View.Count() = 1;\n            Если Result Тогда Name = View.Get(0).Name; Result = ТипЗнч(Name) = Тип("Строка"); КонецЕсли;\n            Если Result Тогда Result = СтрДлина(Name) = 6; КонецЕсли;\n            Если Result Тогда\n                Result = КодСимвола(Name, 1) = 77 И КодСимвола(Name, 2) = 97 И КодСимвола(Name, 3) = 114\n                    И КодСимвола(Name, 4) = 107 И КодСимвола(Name, 5) = 101 И КодСимвола(Name, 6) = 114;\n            КонецЕсли;\n            Если Result Тогда Result = ТипЗнч(View.Get(0).Width) = Тип("Число"); КонецЕсли;\n            Если Result Тогда Result = View.Get(0).Width = 17; КонецЕсли;\n        КонецЕсли;\n        Если Result Тогда Возврат "T"; КонецЕсли;\n'), ('КонецФункции\n\nФункция TreeRowsDiagnosticExperiment()\n    Result = "";\n    Для Part = 1 По 4 Цикл\n        Trit = TreeRowsDiagnosticPart(Part);\n        Если Trit = "?" Тогда Возврат "?"; КонецЕсли;\n        Result = Result + Trit;\n', 'КонецФункции\n\nФункция TreeColumnsDiagnosticExperiment()\n    Result = "";\n    Для Part = 1 По 4 Цикл\n        Trit = TreeColumnsDiagnosticPart(Part);\n        Если Trit = "?" Тогда Возврат "?"; КонецЕсли;\n        Result = Result + Trit;\n'), ('КонецФункции\n\nФункция TreeRowsDiagnosticProbe(Знач Case, Знач Diagnostic)\n    Failed = "1?O0--!..........................................................";\n    Если ТипЗнч(Case) <> Тип("Число") Тогда Возврат Failed; КонецЕсли;\n', 'КонецФункции\n\nФункция TreeColumnsDiagnosticProbe(Знач Case, Знач Diagnostic)\n    Failed = "1?O0--!..........................................................";\n    Если ТипЗнч(Case) <> Тип("Число") Тогда Возврат Failed; КонецЕсли;\n'), ('        Если Code <> 84 И Code <> 70 И Code <> 69 Тогда Возврат Failed; КонецЕсли;\n    КонецЦикла;\n    Возврат "1?D0" + Diagnostic + "!........................................................";\nКонецФункции\n// End isolated Rows view diagnostic.\n\n// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\n', '        Если Code <> 84 И Code <> 70 И Code <> 69 Тогда Возврат Failed; КонецЕсли;\n    КонецЦикла;\n    Возврат "1?K0" + Diagnostic + "!........................................................";\nКонецФункции\n// End isolated Columns view diagnostic.\n\n// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\n'), ('// End bounded ValueTree UnloadColumn observations.\n// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\nTreeRowsDiagnostic = TreeRowsDiagnosticExperiment();\nПоказать("TL01", TreeRowsDiagnosticProbe(1, TreeRowsDiagnostic));\nПоказать("TL02", TreeRowsDiagnosticProbe(2, TreeRowsDiagnostic));\nПоказать("TL03", TreeRowsDiagnosticProbe(3, TreeRowsDiagnostic));\nПоказать("TL04", TreeRowsDiagnosticProbe(4, TreeRowsDiagnostic));\nПоказать("TL05", TreeRowsDiagnosticProbe(5, TreeRowsDiagnostic));\nПоказать("TL06", TreeRowsDiagnosticProbe(6, TreeRowsDiagnostic));\nПоказать("TL07", TreeRowsDiagnosticProbe(7, TreeRowsDiagnostic));\nПоказать("TL08", TreeRowsDiagnosticProbe(8, TreeRowsDiagnostic));\nПоказать("TL09", TreeRowsDiagnosticProbe(9, TreeRowsDiagnostic));\nПоказать("TL10", TreeRowsDiagnosticProbe(10, TreeRowsDiagnostic));\nПоказать("TL11", TreeRowsDiagnosticProbe(11, TreeRowsDiagnostic));\nПоказать("TL12", TreeRowsDiagnosticProbe(12, TreeRowsDiagnostic));\nПоказать("TL13", TreeRowsDiagnosticProbe(13, TreeRowsDiagnostic));\nПоказать("TL14", TreeRowsDiagnosticProbe(14, TreeRowsDiagnostic));\nПоказать("TL15", TreeRowsDiagnosticProbe(15, TreeRowsDiagnostic));\nПоказать("TL16", TreeRowsDiagnosticProbe(16, TreeRowsDiagnostic));\nПоказать("TL17", TreeRowsDiagnosticProbe(17, TreeRowsDiagnostic));\nПоказать("TL18", TreeRowsDiagnosticProbe(18, TreeRowsDiagnostic));\nПоказать("TL19", TreeRowsDiagnosticProbe(19, TreeRowsDiagnostic));\nПоказать("TL20", TreeRowsDiagnosticProbe(20, TreeRowsDiagnostic));\nПоказать("TL21", TreeRowsDiagnosticProbe(21, TreeRowsDiagnostic));\nПоказать("TL22", TreeRowsDiagnosticProbe(22, TreeRowsDiagnostic));\nПоказать("TL23", TreeRowsDiagnosticProbe(23, TreeRowsDiagnostic));\nПоказать("TL24", TreeRowsDiagnosticProbe(24, TreeRowsDiagnostic));\nПоказать("TL25", TreeRowsDiagnosticProbe(25, TreeRowsDiagnostic));\nПоказать("TL26", TreeRowsDiagnosticProbe(26, TreeRowsDiagnostic));\nПоказать("TL27", TreeRowsDiagnosticProbe(27, TreeRowsDiagnostic));\nПоказать("TL28", TreeRowsDiagnosticProbe(28, TreeRowsDiagnostic));\nПоказать("TL29", TreeRowsDiagnosticProbe(29, TreeRowsDiagnostic));\nПоказать("TL30", TreeRowsDiagnosticProbe(30, TreeRowsDiagnostic));\nПоказать("TL31", TreeRowsDiagnosticProbe(31, TreeRowsDiagnostic));\nПоказать("TL32", TreeRowsDiagnosticProbe(32, TreeRowsDiagnostic));\nПоказать("TL33", TreeRowsDiagnosticProbe(33, TreeRowsDiagnostic));\nПоказать("TL34", TreeRowsDiagnosticProbe(34, TreeRowsDiagnostic));\nПоказать("TL35", TreeRowsDiagnosticProbe(35, TreeRowsDiagnostic));\nПоказать("TL36", TreeRowsDiagnosticProbe(36, TreeRowsDiagnostic));\nПоказать("TL37", TreeRowsDiagnosticProbe(37, TreeRowsDiagnostic));\nПоказать("TL38", TreeRowsDiagnosticProbe(38, TreeRowsDiagnostic));\nПоказать("TL39", TreeRowsDiagnosticProbe(39, TreeRowsDiagnostic));\nПоказать("TL40", TreeRowsDiagnosticProbe(40, TreeRowsDiagnostic));\nПоказать("TL41", TreeRowsDiagnosticProbe(41, TreeRowsDiagnostic));\nПоказать("TL42", TreeRowsDiagnosticProbe(42, TreeRowsDiagnostic));\nПоказать("TL43", TreeRowsDiagnosticProbe(43, TreeRowsDiagnostic));\nПоказать("TL44", TreeRowsDiagnosticProbe(44, TreeRowsDiagnostic));\nПоказать("TL45", TreeRowsDiagnosticProbe(45, TreeRowsDiagnostic));\n// End bounded ValueTree LoadColumn observations.\n', '// End bounded ValueTree UnloadColumn observations.\n// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\nTreeColumnsDiagnostic = TreeColumnsDiagnosticExperiment();\nПоказать("TL01", TreeColumnsDiagnosticProbe(1, TreeColumnsDiagnostic));\nПоказать("TL02", TreeColumnsDiagnosticProbe(2, TreeColumnsDiagnostic));\nПоказать("TL03", TreeColumnsDiagnosticProbe(3, TreeColumnsDiagnostic));\nПоказать("TL04", TreeColumnsDiagnosticProbe(4, TreeColumnsDiagnostic));\nПоказать("TL05", TreeColumnsDiagnosticProbe(5, TreeColumnsDiagnostic));\nПоказать("TL06", TreeColumnsDiagnosticProbe(6, TreeColumnsDiagnostic));\nПоказать("TL07", TreeColumnsDiagnosticProbe(7, TreeColumnsDiagnostic));\nПоказать("TL08", TreeColumnsDiagnosticProbe(8, TreeColumnsDiagnostic));\nПоказать("TL09", TreeColumnsDiagnosticProbe(9, TreeColumnsDiagnostic));\nПоказать("TL10", TreeColumnsDiagnosticProbe(10, TreeColumnsDiagnostic));\nПоказать("TL11", TreeColumnsDiagnosticProbe(11, TreeColumnsDiagnostic));\nПоказать("TL12", TreeColumnsDiagnosticProbe(12, TreeColumnsDiagnostic));\nПоказать("TL13", TreeColumnsDiagnosticProbe(13, TreeColumnsDiagnostic));\nПоказать("TL14", TreeColumnsDiagnosticProbe(14, TreeColumnsDiagnostic));\nПоказать("TL15", TreeColumnsDiagnosticProbe(15, TreeColumnsDiagnostic));\nПоказать("TL16", TreeColumnsDiagnosticProbe(16, TreeColumnsDiagnostic));\nПоказать("TL17", TreeColumnsDiagnosticProbe(17, TreeColumnsDiagnostic));\nПоказать("TL18", TreeColumnsDiagnosticProbe(18, TreeColumnsDiagnostic));\nПоказать("TL19", TreeColumnsDiagnosticProbe(19, TreeColumnsDiagnostic));\nПоказать("TL20", TreeColumnsDiagnosticProbe(20, TreeColumnsDiagnostic));\nПоказать("TL21", TreeColumnsDiagnosticProbe(21, TreeColumnsDiagnostic));\nПоказать("TL22", TreeColumnsDiagnosticProbe(22, TreeColumnsDiagnostic));\nПоказать("TL23", TreeColumnsDiagnosticProbe(23, TreeColumnsDiagnostic));\nПоказать("TL24", TreeColumnsDiagnosticProbe(24, TreeColumnsDiagnostic));\nПоказать("TL25", TreeColumnsDiagnosticProbe(25, TreeColumnsDiagnostic));\nПоказать("TL26", TreeColumnsDiagnosticProbe(26, TreeColumnsDiagnostic));\nПоказать("TL27", TreeColumnsDiagnosticProbe(27, TreeColumnsDiagnostic));\nПоказать("TL28", TreeColumnsDiagnosticProbe(28, TreeColumnsDiagnostic));\nПоказать("TL29", TreeColumnsDiagnosticProbe(29, TreeColumnsDiagnostic));\nПоказать("TL30", TreeColumnsDiagnosticProbe(30, TreeColumnsDiagnostic));\nПоказать("TL31", TreeColumnsDiagnosticProbe(31, TreeColumnsDiagnostic));\nПоказать("TL32", TreeColumnsDiagnosticProbe(32, TreeColumnsDiagnostic));\nПоказать("TL33", TreeColumnsDiagnosticProbe(33, TreeColumnsDiagnostic));\nПоказать("TL34", TreeColumnsDiagnosticProbe(34, TreeColumnsDiagnostic));\nПоказать("TL35", TreeColumnsDiagnosticProbe(35, TreeColumnsDiagnostic));\nПоказать("TL36", TreeColumnsDiagnosticProbe(36, TreeColumnsDiagnostic));\nПоказать("TL37", TreeColumnsDiagnosticProbe(37, TreeColumnsDiagnostic));\nПоказать("TL38", TreeColumnsDiagnosticProbe(38, TreeColumnsDiagnostic));\nПоказать("TL39", TreeColumnsDiagnosticProbe(39, TreeColumnsDiagnostic));\nПоказать("TL40", TreeColumnsDiagnosticProbe(40, TreeColumnsDiagnostic));\nПоказать("TL41", TreeColumnsDiagnosticProbe(41, TreeColumnsDiagnostic));\nПоказать("TL42", TreeColumnsDiagnosticProbe(42, TreeColumnsDiagnostic));\nПоказать("TL43", TreeColumnsDiagnosticProbe(43, TreeColumnsDiagnostic));\nПоказать("TL44", TreeColumnsDiagnosticProbe(44, TreeColumnsDiagnostic));\nПоказать("TL45", TreeColumnsDiagnosticProbe(45, TreeColumnsDiagnostic));\n// End bounded ValueTree LoadColumn observations.\n'))


TREE_MOVE_SOURCE_SHA256 = 'a0212150d3d5d2a7252971aa8ba509d439ced04e85b5a157ff1148bf3eff4574'
TREE_MOVE_HELPERS_START = '// Begin bounded ValueTree Move helpers (measurement only; no native answers).\n'
TREE_MOVE_HELPERS_END = '// End bounded ValueTree Move helpers.\n\n'
TREE_MOVE_CALLS_START = '\n// Begin bounded ValueTree Move observations (measurement only; no native answers).\n'
TREE_MOVE_CALLS_END = '// End bounded ValueTree Move observations.\n'


def without_tree_move_probes(text):
    """Exact source-only1022 ->1021 inverse; never alter captured output."""
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != TREE_MOVE_SOURCE_SHA256:
        raise ValueError('tree Move source binding changed')
    for begin, end in ((TREE_MOVE_HELPERS_START, TREE_MOVE_HELPERS_END), (TREE_MOVE_CALLS_START, TREE_MOVE_CALLS_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError('tree Move boundaries changed')
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != TREE_LOAD_RESTORED_SOURCE_SHA256:
        raise ValueError('tree Move baseline binding changed')
    return text


TREE_LOAD_RESTORED_SOURCE_SHA256 = 'ca23e52041022f2085c6cb7d4393a84834e75c69856c756b92e8531ad35c7c3e'
TREE_LOAD_RESTORED_EDITS = (('        ChildRows = R.Rows;\n        Stage = "G";\n        Если T.Rows <> RootRows Тогда ВызватьИсключение "tree-load-root-alias"; КонецЕсли;\n        Stage = "H";\n        Если T.Columns <> Cols Тогда ВызватьИсключение "tree-load-columns-alias"; КонецЕсли;\n        Stage = "I";\n        Если R.Rows <> ChildRows Тогда ВызватьИсключение "tree-load-child-alias"; КонецЕсли;\n        Stage = "J";\n        Если RootRows = Other.Rows Тогда ВызватьИсключение "tree-load-root-distinct"; КонецЕсли;\n        Stage = "K";\n        Если Cols = Other.Columns Тогда ВызватьИсключение "tree-load-columns-distinct"; КонецЕсли;\n        Stage = "L";\n        Если ChildRows = OtherRow.Rows Тогда ВызватьИсключение "tree-load-child-distinct"; КонецЕсли;\n        Stage = "M";\n        Если R <> T.Rows.Get(0) Тогда ВызватьИсключение "tree-load-row-alias"; КонецЕсли;\n', '        ChildRows = R.Rows;\n        Stage = "G";\n        Expected = TreeLoadPair(R, OtherRow); Empty = Новый Массив;\n        TreeLoadRows(RootRows, Expected, Неопределено); TreeLoadRows(T.Rows, Expected, Неопределено);\n        Stage = "H";\n        Если T.Columns <> Cols Тогда ВызватьИсключение "tree-load-columns-alias"; КонецЕсли;\n        Stage = "I";\n        TreeLoadRows(ChildRows, Empty, R); TreeLoadRows(R.Rows, Empty, R);\n        Stage = "J";\n        TreeLoadRows(RootRows, Expected, Неопределено); TreeLoadRows(Other.Rows, Empty, Неопределено);\n        Stage = "K";\n        Если Cols = Other.Columns Тогда ВызватьИсключение "tree-load-columns-distinct"; КонецЕсли;\n        Stage = "L";\n        TreeLoadRows(ChildRows, Empty, R); TreeLoadRows(OtherRow.Rows, Empty, OtherRow);\n        Stage = "M";\n        Если R <> T.Rows.Get(0) Тогда ВызватьИсключение "tree-load-row-alias"; КонецЕсли;\n'), ('\nПроцедура TreeLoadRows(Знач Rows, Знач Expected, Знач Parent)\n    TreeLoadCount(Rows, Expected.Count());\n    Если Rows.Parent <> Parent Тогда ВызватьИсключение "tree-load-collection-parent"; КонецЕсли;\n', '\nПроцедура TreeLoadRows(Знач Rows, Знач Expected, Знач Parent)\n    Если ТипЗнч(Rows) <> Тип("КоллекцияСтрокДереваЗначений") Тогда ВызватьИсключение "tree-load-rows-type"; КонецЕсли;\n    TreeLoadCount(Rows, Expected.Count());\n    Если Rows.Parent <> Parent Тогда ВызватьИсключение "tree-load-collection-parent"; КонецЕсли;\n'), ('\nФункция TreeLoadSnapshot(Знач S, Знач Source, Знач Original, Знач Refs)\n    Если S.Tree.Columns <> S.ColumnCollection Или S.Tree.Rows <> S.RowCollections[0]\n        Или S.Foreign.Columns <> S.ForeignColumnCollection Или S.Foreign.Rows <> S.ForeignRowCollection Тогда\n        ВызватьИсключение "tree-load-retained-collection";\n    КонецЕсли;\n', '\nФункция TreeLoadSnapshot(Знач S, Знач Source, Знач Original, Знач Refs)\n    Если S.Tree.Columns <> S.ColumnCollection\n        Или S.Foreign.Columns <> S.ForeignColumnCollection Тогда\n        ВызватьИсключение "tree-load-retained-collection";\n    КонецЕсли;\n'), ('    TreeLoadSchema(S.Foreign, S.ForeignColumns, S.ForeignNames, Ложь);\n    Empty = Новый Массив; TreeLoadRows(S.Foreign.Rows, Empty, Неопределено);\n    Если S.Nodes.Count() = 0 Тогда\n        TreeLoadRows(S.Tree.Rows, Empty, Неопределено);\n        Text = S.Mode + S.Mode + "................................................";\n    Иначе\n        TreeLoadCount(S.Nodes, 6); TreeLoadRows(S.Tree.Rows, TreeLoadPair(S.Nodes[0], S.Nodes[1]), Неопределено);\n        Text = "BB";\n        Для P = 0 По 5 Цикл\n            R = S.Nodes[P];\n            Если R.Rows <> S.RowCollections[P + 1] Тогда ВызватьИсключение "tree-load-retained-child"; КонецЕсли;\n            Parent = Неопределено; Children = Новый Массив;\n            Если P = 0 Тогда Children = TreeLoadPair(S.Nodes[3], S.Nodes[4]);\n', '    TreeLoadSchema(S.Foreign, S.ForeignColumns, S.ForeignNames, Ложь);\n    Empty = Новый Массив; TreeLoadRows(S.Foreign.Rows, Empty, Неопределено);\n    TreeLoadRows(S.ForeignRowCollection, Empty, Неопределено);\n    Если S.Nodes.Count() = 0 Тогда\n        TreeLoadRows(S.Tree.Rows, Empty, Неопределено);\n        TreeLoadRows(S.RowCollections[0], Empty, Неопределено);\n        Text = S.Mode + S.Mode + "................................................";\n    Иначе\n        TreeLoadCount(S.Nodes, 6); TreeLoadRows(S.Tree.Rows, TreeLoadPair(S.Nodes[0], S.Nodes[1]), Неопределено);\n        TreeLoadRows(S.RowCollections[0], TreeLoadPair(S.Nodes[0], S.Nodes[1]), Неопределено);\n        Text = "BB";\n        Для P = 0 По 5 Цикл\n            R = S.Nodes[P];\n            Parent = Неопределено; Children = Новый Массив;\n            Если P = 0 Тогда Children = TreeLoadPair(S.Nodes[3], S.Nodes[4]);\n'), ('            Если R.Owner() <> S.Tree Или R.Parent <> Parent Тогда ВызватьИсключение "tree-load-row-links"; КонецЕсли;\n            TreeLoadRows(R.Rows, Children, R);\n            Для C = 0 По 3 Цикл Text = Text + TreeLoadCell(R.Get(C), Refs); КонецЦикла;\n        КонецЦикла;\n', '            Если R.Owner() <> S.Tree Или R.Parent <> Parent Тогда ВызватьИсключение "tree-load-row-links"; КонецЕсли;\n            TreeLoadRows(R.Rows, Children, R);\n            TreeLoadRows(S.RowCollections[P + 1], Children, R);\n            Для C = 0 По 3 Цикл Text = Text + TreeLoadCell(R.Get(C), Refs); КонецЦикла;\n        КонецЦикла;\n'), ('// End bounded ValueTree UnloadColumn observations.\n// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\nTreeColumnsDiagnostic = TreeColumnsDiagnosticExperiment();\nПоказать("TL01", TreeColumnsDiagnosticProbe(1, TreeColumnsDiagnostic));\nПоказать("TL02", TreeColumnsDiagnosticProbe(2, TreeColumnsDiagnostic));\nПоказать("TL03", TreeColumnsDiagnosticProbe(3, TreeColumnsDiagnostic));\nПоказать("TL04", TreeColumnsDiagnosticProbe(4, TreeColumnsDiagnostic));\nПоказать("TL05", TreeColumnsDiagnosticProbe(5, TreeColumnsDiagnostic));\nПоказать("TL06", TreeColumnsDiagnosticProbe(6, TreeColumnsDiagnostic));\nПоказать("TL07", TreeColumnsDiagnosticProbe(7, TreeColumnsDiagnostic));\nПоказать("TL08", TreeColumnsDiagnosticProbe(8, TreeColumnsDiagnostic));\nПоказать("TL09", TreeColumnsDiagnosticProbe(9, TreeColumnsDiagnostic));\nПоказать("TL10", TreeColumnsDiagnosticProbe(10, TreeColumnsDiagnostic));\nПоказать("TL11", TreeColumnsDiagnosticProbe(11, TreeColumnsDiagnostic));\nПоказать("TL12", TreeColumnsDiagnosticProbe(12, TreeColumnsDiagnostic));\nПоказать("TL13", TreeColumnsDiagnosticProbe(13, TreeColumnsDiagnostic));\nПоказать("TL14", TreeColumnsDiagnosticProbe(14, TreeColumnsDiagnostic));\nПоказать("TL15", TreeColumnsDiagnosticProbe(15, TreeColumnsDiagnostic));\nПоказать("TL16", TreeColumnsDiagnosticProbe(16, TreeColumnsDiagnostic));\nПоказать("TL17", TreeColumnsDiagnosticProbe(17, TreeColumnsDiagnostic));\nПоказать("TL18", TreeColumnsDiagnosticProbe(18, TreeColumnsDiagnostic));\nПоказать("TL19", TreeColumnsDiagnosticProbe(19, TreeColumnsDiagnostic));\nПоказать("TL20", TreeColumnsDiagnosticProbe(20, TreeColumnsDiagnostic));\nПоказать("TL21", TreeColumnsDiagnosticProbe(21, TreeColumnsDiagnostic));\nПоказать("TL22", TreeColumnsDiagnosticProbe(22, TreeColumnsDiagnostic));\nПоказать("TL23", TreeColumnsDiagnosticProbe(23, TreeColumnsDiagnostic));\nПоказать("TL24", TreeColumnsDiagnosticProbe(24, TreeColumnsDiagnostic));\nПоказать("TL25", TreeColumnsDiagnosticProbe(25, TreeColumnsDiagnostic));\nПоказать("TL26", TreeColumnsDiagnosticProbe(26, TreeColumnsDiagnostic));\nПоказать("TL27", TreeColumnsDiagnosticProbe(27, TreeColumnsDiagnostic));\nПоказать("TL28", TreeColumnsDiagnosticProbe(28, TreeColumnsDiagnostic));\nПоказать("TL29", TreeColumnsDiagnosticProbe(29, TreeColumnsDiagnostic));\nПоказать("TL30", TreeColumnsDiagnosticProbe(30, TreeColumnsDiagnostic));\nПоказать("TL31", TreeColumnsDiagnosticProbe(31, TreeColumnsDiagnostic));\nПоказать("TL32", TreeColumnsDiagnosticProbe(32, TreeColumnsDiagnostic));\nПоказать("TL33", TreeColumnsDiagnosticProbe(33, TreeColumnsDiagnostic));\nПоказать("TL34", TreeColumnsDiagnosticProbe(34, TreeColumnsDiagnostic));\nПоказать("TL35", TreeColumnsDiagnosticProbe(35, TreeColumnsDiagnostic));\nПоказать("TL36", TreeColumnsDiagnosticProbe(36, TreeColumnsDiagnostic));\nПоказать("TL37", TreeColumnsDiagnosticProbe(37, TreeColumnsDiagnostic));\nПоказать("TL38", TreeColumnsDiagnosticProbe(38, TreeColumnsDiagnostic));\nПоказать("TL39", TreeColumnsDiagnosticProbe(39, TreeColumnsDiagnostic));\nПоказать("TL40", TreeColumnsDiagnosticProbe(40, TreeColumnsDiagnostic));\nПоказать("TL41", TreeColumnsDiagnosticProbe(41, TreeColumnsDiagnostic));\nПоказать("TL42", TreeColumnsDiagnosticProbe(42, TreeColumnsDiagnostic));\nПоказать("TL43", TreeColumnsDiagnosticProbe(43, TreeColumnsDiagnostic));\nПоказать("TL44", TreeColumnsDiagnosticProbe(44, TreeColumnsDiagnostic));\nПоказать("TL45", TreeColumnsDiagnosticProbe(45, TreeColumnsDiagnostic));\n// End bounded ValueTree LoadColumn observations.\n', '// End bounded ValueTree UnloadColumn observations.\n// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\nПоказать("TL01", TreeLoadProbe(1));\nПоказать("TL02", TreeLoadProbe(2));\nПоказать("TL03", TreeLoadProbe(3));\nПоказать("TL04", TreeLoadProbe(4));\nПоказать("TL05", TreeLoadProbe(5));\nПоказать("TL06", TreeLoadProbe(6));\nПоказать("TL07", TreeLoadProbe(7));\nПоказать("TL08", TreeLoadProbe(8));\nПоказать("TL09", TreeLoadProbe(9));\nПоказать("TL10", TreeLoadProbe(10));\nПоказать("TL11", TreeLoadProbe(11));\nПоказать("TL12", TreeLoadProbe(12));\nПоказать("TL13", TreeLoadProbe(13));\nПоказать("TL14", TreeLoadProbe(14));\nПоказать("TL15", TreeLoadProbe(15));\nПоказать("TL16", TreeLoadProbe(16));\nПоказать("TL17", TreeLoadProbe(17));\nПоказать("TL18", TreeLoadProbe(18));\nПоказать("TL19", TreeLoadProbe(19));\nПоказать("TL20", TreeLoadProbe(20));\nПоказать("TL21", TreeLoadProbe(21));\nПоказать("TL22", TreeLoadProbe(22));\nПоказать("TL23", TreeLoadProbe(23));\nПоказать("TL24", TreeLoadProbe(24));\nПоказать("TL25", TreeLoadProbe(25));\nПоказать("TL26", TreeLoadProbe(26));\nПоказать("TL27", TreeLoadProbe(27));\nПоказать("TL28", TreeLoadProbe(28));\nПоказать("TL29", TreeLoadProbe(29));\nПоказать("TL30", TreeLoadProbe(30));\nПоказать("TL31", TreeLoadProbe(31));\nПоказать("TL32", TreeLoadProbe(32));\nПоказать("TL33", TreeLoadProbe(33));\nПоказать("TL34", TreeLoadProbe(34));\nПоказать("TL35", TreeLoadProbe(35));\nПоказать("TL36", TreeLoadProbe(36));\nПоказать("TL37", TreeLoadProbe(37));\nПоказать("TL38", TreeLoadProbe(38));\nПоказать("TL39", TreeLoadProbe(39));\nПоказать("TL40", TreeLoadProbe(40));\nПоказать("TL41", TreeLoadProbe(41));\nПоказать("TL42", TreeLoadProbe(42));\nПоказать("TL43", TreeLoadProbe(43));\nПоказать("TL44", TreeLoadProbe(44));\nПоказать("TL45", TreeLoadProbe(45));\n// End bounded ValueTree LoadColumn observations.\n'))


def without_tree_load_restoration(text):
    """Exact restored observation source -> public Columns source; no output edits."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_LOAD_RESTORED_SOURCE_SHA256:
        raise ValueError("tree restored observation source binding changed")
    for before, after in reversed(TREE_LOAD_RESTORED_EDITS):
        if text.count(after) != 1:
            raise ValueError("tree restored observation inverse changed")
        text = text.replace(after, before, 1)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_COLUMNS_DIAGNOSTIC_SOURCE_SHA256:
        raise ValueError("tree restored observation baseline changed")
    return text


def without_tree_columns_diagnostic(text):
    """Exact fail-only Columns source -> public Rows source; no output edits."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() == TREE_LOAD_RESTORED_SOURCE_SHA256:
        text = without_tree_load_restoration(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_COLUMNS_DIAGNOSTIC_SOURCE_SHA256:
        raise ValueError("tree Columns diagnostic source binding changed")
    for before, after in reversed(TREE_COLUMNS_DIAGNOSTIC_EDITS):
        if text.count(after) != 1:
            raise ValueError("tree Columns diagnostic inverse changed")
        text = text.replace(after, before, 1)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256:
        raise ValueError("tree Columns diagnostic baseline changed")
    return text


def without_tree_rows_diagnostic(text):
    """Exact fail-only Rows source -> public calibration source; no output edits."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() == TREE_LOAD_RESTORED_SOURCE_SHA256:
        text = without_tree_load_restoration(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() == TREE_COLUMNS_DIAGNOSTIC_SOURCE_SHA256:
        text = without_tree_columns_diagnostic(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256:
        raise ValueError("tree Rows diagnostic source binding changed")
    for before, after in reversed(TREE_ROWS_DIAGNOSTIC_EDITS):
        if text.count(after) != 1:
            raise ValueError("tree Rows diagnostic inverse changed")
        text = text.replace(after, before, 1)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_LOAD_CALIBRATION_SOURCE_SHA256:
        raise ValueError("tree Rows diagnostic baseline changed")
    return text


def without_tree_load_calibration(text):
    """Exact diagnostic source -> original public measurement; never edit output."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() == TREE_LOAD_RESTORED_SOURCE_SHA256:
        text = without_tree_load_restoration(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() == TREE_COLUMNS_DIAGNOSTIC_SOURCE_SHA256:
        text = without_tree_columns_diagnostic(text)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() == TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256:
        text = without_tree_rows_diagnostic(text)
        raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_LOAD_CALIBRATION_SOURCE_SHA256:
        raise ValueError("tree LoadColumn calibration source binding changed")
    for before, after in reversed(TREE_LOAD_CALIBRATION_EDITS):
        if text.count(after) != 1:
            raise ValueError("tree LoadColumn calibration inverse changed")
        text = text.replace(after, before, 1)
    raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != TREE_LOAD_ORIGINAL_SOURCE_SHA256:
        raise ValueError("tree LoadColumn calibration baseline changed")
    return text


def without_tree_load_probes(text):
    """Exact current source -> collections976; never edit captured outputs."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() == TREE_LOAD_RESTORED_SOURCE_SHA256:
        text = without_tree_load_restoration(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() == TREE_COLUMNS_DIAGNOSTIC_SOURCE_SHA256:
        text = without_tree_columns_diagnostic(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() == TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256:
        text = without_tree_rows_diagnostic(text)
        raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() == TREE_LOAD_CALIBRATION_SOURCE_SHA256:
        text = without_tree_load_calibration(text)
        raw = text.encode("utf-8") if text.startswith("\ufeff") else text.encode("utf-8-sig")
    if hashlib.sha256(raw).hexdigest() != '0f36f76a44f63f9623a3c204c5cace3dd4d4328b4465f3bb002f660fc96e684b':
        raise ValueError('tree LoadColumn source binding changed')
    if not text.endswith(TREE_LOAD_CALLS_END):
        raise ValueError('tree LoadColumn tail changed')
    for begin, end in ((TREE_LOAD_HELPERS_START, TREE_LOAD_HELPERS_END), (TREE_LOAD_CALLS_START, TREE_LOAD_CALLS_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError('tree LoadColumn boundaries changed')
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4':
        raise ValueError('tree LoadColumn baseline binding changed')
    return text


TREE_UNLOAD_HELPERS_START = '// Begin bounded ValueTree UnloadColumn helpers (measurement only; no native answers).\n'
TREE_UNLOAD_HELPERS_END = '// End bounded ValueTree UnloadColumn helpers.\n\n'
TREE_UNLOAD_CALLS_START = '\n// Begin bounded ValueTree UnloadColumn observations (measurement only; no native answers).\n'
TREE_UNLOAD_CALLS_END = '// End bounded ValueTree UnloadColumn observations.\n'


TREE_UNLOAD_SUPPLEMENT = 'Показать("tree.unload.selector.fraction-one-half", TreeUnloadProbe("S.Tree.Rows.UnloadColumn(1.5)"));\nПоказать("tree.unload.selector.fraction-one-nine", TreeUnloadProbe("S.Tree.Rows.UnloadColumn(1.9)"));\nПоказать("tree.unload.selector.fraction-negative-half", TreeUnloadProbe("S.Tree.Rows.UnloadColumn(-0.5)"));\n'


def without_tree_unload_supplement(text):
    """Exact source-only collections976 -> 973 inverse; no native output edits."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    if TREE_LOAD_HELPERS_START in text or TREE_LOAD_CALLS_START in text:
        text = without_tree_load_probes(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4':
        raise ValueError('tree UnloadColumn supplement source binding changed')
    if text.count(TREE_UNLOAD_SUPPLEMENT) != 1:
        raise ValueError('tree UnloadColumn supplement boundary changed')
    text = text.replace(TREE_UNLOAD_SUPPLEMENT, '', 1)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != 'bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada':
        raise ValueError('tree UnloadColumn original27 binding changed')
    return text


def without_tree_unload_probes(text):
    """Exact source-only collections973 -> 946 inverse; never edit native output."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    if TREE_LOAD_HELPERS_START in text or TREE_LOAD_CALLS_START in text:
        text = without_tree_load_probes(text)
    if 'tree.unload.selector.fraction-one-half' in text:
        text = without_tree_unload_supplement(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != 'bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada':
        raise ValueError('tree UnloadColumn source binding changed')
    if not text.endswith(TREE_UNLOAD_CALLS_END):
        raise ValueError('tree UnloadColumn tail changed')
    for begin, end in ((TREE_UNLOAD_HELPERS_START, TREE_UNLOAD_HELPERS_END),
                       (TREE_UNLOAD_CALLS_START, TREE_UNLOAD_CALLS_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError('tree UnloadColumn boundaries changed')
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3':
        raise ValueError('tree UnloadColumn baseline binding changed')
    return text


TREE_FIND_HELPERS_START = '// Begin bounded ValueTree Find helpers (measurement only; no native answers).\n'
TREE_FIND_HELPERS_END = '// End bounded ValueTree Find helpers.\n\n'
TREE_FIND_CALLS_START = '// Begin bounded ValueTree Find observations (measurement only; no native answers).\n'
TREE_FIND_CALLS_END = '// End bounded ValueTree Find observations.\n'


def without_tree_find_probes(text):
    """Exact source-only collections946 -> 902 inverse; never edit native output."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    if TREE_UNLOAD_HELPERS_START in text or TREE_UNLOAD_CALLS_START in text:
        text = without_tree_unload_probes(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3':
        raise ValueError('tree Find source binding changed')
    if not text.endswith(TREE_FIND_CALLS_END):
        raise ValueError('tree Find tail changed')
    for begin, end in ((TREE_FIND_HELPERS_START, TREE_FIND_HELPERS_END),
                       (TREE_FIND_CALLS_START, TREE_FIND_CALLS_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError('tree Find boundaries changed')
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782':
        raise ValueError('tree Find baseline binding changed')
    return text


TREE_FINDROWS_HELPERS_START = '// Begin bounded ValueTree FindRows helpers (measurement only; no native answers).\n'
TREE_FINDROWS_HELPERS_END = '// End bounded ValueTree FindRows helpers.\n\n'
TREE_FINDROWS_CALLS_START = '// Begin bounded ValueTree FindRows observations (measurement only; no native answers).\n'
TREE_FINDROWS_CALLS_END = '// End bounded ValueTree FindRows observations.\n'


def without_tree_findrows_probes(text):
    """Exact source-only collections902 -> 866 inverse; never edit native output."""
    if TREE_MOVE_HELPERS_START in text or TREE_MOVE_CALLS_START in text:
        text = without_tree_move_probes(text)
    if TREE_FIND_HELPERS_START in text or TREE_FIND_CALLS_START in text:
        text = without_tree_find_probes(text)
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != '5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782':
        raise ValueError('tree FindRows source binding changed')
    if not text.endswith(TREE_FINDROWS_CALLS_END):
        raise ValueError('tree FindRows tail changed')
    for begin, end in ((TREE_FINDROWS_HELPERS_START, TREE_FINDROWS_HELPERS_END),
                       (TREE_FINDROWS_CALLS_START, TREE_FINDROWS_CALLS_END)):
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError('tree FindRows boundaries changed')
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8') if text.startswith('\ufeff') else text.encode('utf-8-sig')
    if hashlib.sha256(raw).hexdigest() != 'b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27':
        raise ValueError('tree FindRows baseline binding changed')
    return text


VALUE_TREE_START = '// Begin bounded ValueTree core observations (candidate; not native evidence).\n'
VALUE_TREE_END = '// End bounded ValueTree core observations.\n'


def without_value_tree_probes(text):
    """Exact source inverse for old captures only; never truncate native output."""
    if TREE_FINDROWS_HELPERS_START in text or TREE_FINDROWS_CALLS_START in text:
        text = without_tree_findrows_probes(text)
    raw = text.encode('utf-8-sig') if not text.startswith('\ufeff') else text.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != 'b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27':
        raise ValueError('value tree source binding changed')
    if text.count(VALUE_TREE_START) != 1 or text.count(VALUE_TREE_END) != 1 or not text.endswith(VALUE_TREE_END):
        raise ValueError('value tree boundaries changed')
    result = text.split(VALUE_TREE_START, 1)[0]
    raw = result.encode('utf-8-sig') if not result.startswith('\ufeff') else result.encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != '42c1fedddb8a689f3ba2ca6a241b1d19d38c0bea4da8a29e5934b3082a43fdfb':
        raise ValueError('value tree baseline binding changed')
    return result


def without_fill_exclude_order_probes(text):
    """Restore the exact 852-record PR87 source, never truncate native outputs."""
    if VALUE_TREE_START in text or VALUE_TREE_END in text:
        text = without_value_tree_probes(text)
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != '42c1fedddb8a689f3ba2ca6a241b1d19d38c0bea4da8a29e5934b3082a43fdfb':
        raise ValueError('fill exclude order source binding changed')
    for start, end in FILL_EXCLUDE_ORDER_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('fill exclude order probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9':
        raise ValueError('fill exclude order baseline binding changed')
    return text


FILL_EXCLUDE_PROBE_BLOCKS = (
    ('// Begin FillPropertyValues EXCLUDE checkpoint helpers.\n',
     '// End FillPropertyValues EXCLUDE checkpoint helpers.\n\n'),
    ('// Begin FillPropertyValues EXCLUDE checkpoint observations.\n',
     '// End FillPropertyValues EXCLUDE checkpoint observations.\n'),
)


def without_fill_exclude_probes(text):
    """Restore all 841 records' source; never truncate observed output."""
    if any(boundary in text for pair in FILL_EXCLUDE_ORDER_PROBE_BLOCKS for boundary in pair):
        text = without_fill_exclude_order_probes(text)
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9':
        raise ValueError('fill exclude source binding changed')
    for start, end in FILL_EXCLUDE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('fill exclude probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232':
        raise ValueError('fill exclude baseline source binding changed')
    return text


FILL_INCLUDE_PROBE_BLOCKS = (
    ('// Begin FillPropertyValues INCLUDE checkpoint helpers.\n',
     '// End FillPropertyValues INCLUDE checkpoint helpers.\n\n'),
    ('// Begin FillPropertyValues INCLUDE checkpoint observations.\n',
     '// End FillPropertyValues INCLUDE checkpoint observations.\n'),
)


def without_fill_include_probes(text):
    """Restore all 828 native-verified records' source with an exact byte pin."""
    if any(boundary in text for pair in (*FILL_EXCLUDE_ORDER_PROBE_BLOCKS, *FILL_EXCLUDE_PROBE_BLOCKS) for boundary in pair):
        text = without_fill_exclude_probes(text)
    for start, end in FILL_INCLUDE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('fill include probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'b3bf181de84a575335ce7e4794ced459ad252eb7853cc42095fb62521dc6a409':
        raise ValueError('fill include baseline source binding changed')
    return text


DESCRIPTOR_MAP_PROBE_BLOCKS = (
    ('// Begin descriptor Map-key checkpoint helpers.\n',
     '// End descriptor Map-key checkpoint helpers.\n\n'),
    ('// Begin descriptor Map-key checkpoint observations.\n',
     '// End descriptor Map-key checkpoint observations.\n'),
)


def without_descriptor_map_probes(text):
    """Restore every byte of the native-verified 797-message source."""
    if any(boundary in text for pair in FILL_INCLUDE_PROBE_BLOCKS for boundary in pair):
        text = without_fill_include_probes(text)
    for start, end in DESCRIPTOR_MAP_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('descriptor map probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if not raw.startswith(b'\xef\xbb\xbf'):
        raw = b'\xef\xbb\xbf' + raw
    if hashlib.sha256(raw).hexdigest() != 'f8a5be47e937e39500c51a2b9c8fdaaf4becd68aa908cf7e99abe068a6c8cd4a':
        raise ValueError('descriptor map baseline source binding changed')
    return text


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def historical_collections_source(source, output):
    """Exact source-bound replay, not a current-output prefix exception.

    The complete current scenario is separately mandatory in live Docker CI.
    Only line-ending transport is normalized, including for source binding.
    """
    source = source.replace(b"\r\n", b"\n")
    output = output.replace(b"\r\n", b"\n")
    if git_blob(output) != HISTORICAL_COLLECTIONS_OUTPUT_BLOB:
        raise ValueError("historical collections output binding changed")
    text = without_field_reference_probes(without_descriptor_map_probes(source.decode("utf-8-sig")))
    for start, end in FINAL_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("historical collections probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    replay = ("\ufeff" + text).encode("utf-8")
    if git_blob(replay) != HISTORICAL_COLLECTIONS_BLOB:
        raise ValueError("historical collections source binding changed")
    return replay



# The six historical Windows captures are immutable. Live CI executes all probes.
HISTORICAL_VALUES_BLOB = '5b7f3976c2d6de30930c83063079d7e2e41317e5'
HISTORICAL_VALUES_OUTPUT_BLOB = '016f30d6f3bdb1a814e86a70e3bcf424383a0d27'
CHARS_PROBE_BLOCKS = (('// Begin Chars namespace helpers.\n', '// End Chars namespace helpers.\n\n'), ('// Begin Chars namespace observations.\n', '// End Chars namespace observations.\n'))


def without_chars_probes(text):
    """Remove only bounded Chars additions; historical caller checks exact hash."""
    for start, end in CHARS_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("Chars probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    return text


FIXED_STRING_PROBE_BLOCKS = (
    ('// Begin fixed String default helpers.\n', '// End fixed String default helpers.\n\n'),
    ('// Begin fixed String default observations.\n', '// End fixed String default observations.\n'),
)


SERVICE_FILLED_PROBE_BLOCK = (
    '// Begin service ValueIsFilled observations.\n',
    '// End service ValueIsFilled observations.\n',
)


NSTR_PROBE_BLOCKS = (
    ('// Begin bounded NStr helpers (measurement only; no native answers).\n', '// End bounded NStr helpers.\n\n'),
    ('// Begin bounded NStr observations (measurement only; no native answers).\n', '// End bounded NStr observations.\n'),
)


NSTR_DISCRIMINATOR_BLOCK = (
    '// Begin bounded NStr discriminators (measurement only; no native answers).\n',
    '// End bounded NStr discriminators.\n',
)


def without_nstr_discriminators(text):
    """Exact values534-to-521 source inverse; never edit any native output."""
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5':
        raise ValueError('NStr discriminator candidate source binding changed')
    start, end = NSTR_DISCRIMINATOR_BLOCK
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('NStr discriminator boundaries changed')
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '9e1af33c93352aebf9166bf5f702f526f221df7e9945ba139ccbc3d1fd0a34e4':
        raise ValueError('NStr discriminator historical source binding changed')
    return text


def without_nstr_probes(text):
    """Exact values521-to-485 source inverse; never filter output or admit old input."""
    if any(boundary in text for boundary in NSTR_DISCRIMINATOR_BLOCK):
        text = without_nstr_discriminators(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '9e1af33c93352aebf9166bf5f702f526f221df7e9945ba139ccbc3d1fd0a34e4':
        raise ValueError('NStr candidate source binding changed')
    for start, end in NSTR_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('NStr probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76':
        raise ValueError('NStr historical source binding changed')
    return text


TEXT_DOCUMENT_PROBE_BLOCKS = (
    ('// Begin bounded TextDocument helpers (measurement only; no native answers).\n', '// End bounded TextDocument helpers.\n\n\n'),
    ('// Begin bounded TextDocument observations (measurement only; no native answers).\n', '// End bounded TextDocument observations.\n'),
)


def without_text_document_probes(text):
    """Restore exact values441 source; never filter outputs or admit old source."""
    if any(boundary in text for pair in NSTR_PROBE_BLOCKS for boundary in pair):
        text = without_nstr_probes(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76':
        raise ValueError('TextDocument candidate source binding changed')
    for start, end in TEXT_DOCUMENT_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('TextDocument probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c':
        raise ValueError('TextDocument historical source binding changed')
    return text


UUID_PROBE_BLOCKS = (
    ('// Begin bounded UUID codec helpers (candidate; not native evidence).\n', '// End bounded UUID codec helpers.\n\n'),
    ('// Begin bounded UUID codec observations (candidate; not native evidence).\n', '// End bounded UUID codec observations.\n'),
    ('// Begin bounded UUID helpers (candidate; not native evidence).\n', '// End bounded UUID helpers.\n\n'),
    ('// Begin bounded UUID observations (candidate; not native evidence).\n', '// End bounded UUID observations.\n'),
)


def without_uuid_probes(text):
    """Offline historical replay only; exact input/output hashes, never admission."""
    if any(boundary in text for pair in TEXT_DOCUMENT_PROBE_BLOCKS for boundary in pair):
        text = without_text_document_probes(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c':
        raise ValueError('UUID candidate source binding changed')
    for start, end in UUID_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('UUID probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12':
        raise ValueError('UUID historical source binding changed')
    return text


def without_service_filled_probes(text):
    """Restore the exact native-verified 377-record source, not an output prefix."""
    if any(boundary in text for pair in UUID_PROBE_BLOCKS for boundary in pair):
        text = without_uuid_probes(text)
    start, end = SERVICE_FILLED_PROBE_BLOCK
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("service filled probe boundaries changed")
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != 'eaf36b0deed933ea1c3eabcfbde0be59f2f1d8bf6b07b5533f4df2e8cc967b45':
        raise ValueError("service filled baseline source binding changed")
    return text


def without_fixed_string_probes(text):
    """Restore the exact native-verified 361-record Chars source."""
    if any(boundary in text for boundary in SERVICE_FILLED_PROBE_BLOCK):
        text = without_service_filled_probes(text)
    for start, end in FIXED_STRING_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError("fixed String probe boundaries changed")
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != '5fd00b472332044f4bae4c12973bcc66c074b27f7c98fe58b21b149088166fff':
        raise ValueError("fixed String baseline source binding changed")
    return text


def historical_values_source(source, output):
    """Reconstruct every byte of original values source, never an output prefix."""
    source = source.replace(b"\r\n", b"\n")
    output = output.replace(b"\r\n", b"\n")
    if git_blob(output) != HISTORICAL_VALUES_OUTPUT_BLOB:
        raise ValueError("historical values output binding changed")
    replay = without_chars_probes(without_fixed_string_probes(source.decode("utf-8"))).encode("utf-8")
    if git_blob(replay) != HISTORICAL_VALUES_BLOB:
        raise ValueError("historical values source binding changed")
    return replay


# Windows dates capture predates the appended fixed-GMT fractional probes.
HISTORICAL_DATES_BLOB = '1527fe4c52feab97bc6ed8ba007cf664b4565cc6'
CURRENT_DATES_BLOB = 'd6d03bd014466f41d49ab566c003ac680cd052b2'
HISTORICAL_DATES_OUTPUT_BLOB = '05d23c46540b301820f2ac81c8a67fc0e1273dc8'

def historical_dates_source(source: bytes, output: bytes) -> bytes:
    """Reconstruct the exact captured source, never filter observed output."""
    source = source.replace(b'\r\n', b'\n')
    output = output.replace(b'\r\n', b'\n')
    if git_blob(source) != CURRENT_DATES_BLOB or git_blob(output) != HISTORICAL_DATES_OUTPUT_BLOB:
        raise ValueError('Historical dates source/output identity mismatch')
    historical = source[:15403]
    if git_blob(historical) != HISTORICAL_DATES_BLOB:
        raise ValueError('Historical dates reconstruction mismatch')
    return historical


# Windows numbers capture predates the exact-half division source-only suffix.
HISTORICAL_NUMBERS_BLOB = 'abc35547f3603ce67e958a127aeb2f3bb42acca3'
CURRENT_NUMBERS_BLOB = '25931bcb4a9636c6fcf22b16cb9023a243708751'
HISTORICAL_NUMBERS_OUTPUT_BLOB = 'ab5000e748f5b8652a920ddcb2fc85eab8cf7e13'


def historical_numbers_source(source: bytes, output: bytes) -> bytes:
    """Replay all 350 captured observations against their exact original source."""
    source = source.replace(b'\r\n', b'\n')
    output = output.replace(b'\r\n', b'\n')
    if git_blob(source) != CURRENT_NUMBERS_BLOB or git_blob(output) != HISTORICAL_NUMBERS_OUTPUT_BLOB:
        raise ValueError('Historical numbers source/output identity mismatch')
    historical = source[:42360]
    if git_blob(historical) != HISTORICAL_NUMBERS_BLOB:
        raise ValueError('Historical numbers reconstruction mismatch')
    return historical


# Only the new exception source is removed for the complete frozen 88-record replay.
# Native full-suite runs never call this projection and always execute all probes.
HISTORICAL_FUNCTIONS_BLOB = 'c83e860364555a0f6290e3b34d7cf8a8eb40df9f'
HISTORICAL_FUNCTIONS_OUTPUT_BLOB = '6df192ac9d10c07755948d7c14cfed9e2311c65f'
EXTENDED_EXCEPTION_PROBE_BLOCKS = (
    ('// Begin extended exception checkpoint helpers.\n',
     '// End extended exception checkpoint helpers.\n\n'),
    ('// Begin extended exception checkpoint observations.\n',
     '// End extended exception checkpoint observations.\n'),
)


def without_extended_exception_probes(text):
    """Restore the exact complete source of all 88 historical function records."""
    if any(boundary in text for pair in EXCEPTION_CONTEXT_PROBE_BLOCKS for boundary in pair):
        text = without_exception_context_probes(text)
    for start, end in EXTENDED_EXCEPTION_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('extended exception probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != HISTORICAL_FUNCTIONS_BLOB:
        raise ValueError('extended exception baseline source binding changed')
    return text


def historical_functions_source(source, output):
    """Replay the complete immutable Windows capture, not an output-prefix pass."""
    source = source.replace(b'\r\n', b'\n')
    output = output.replace(b'\r\n', b'\n')
    if git_blob(output) != HISTORICAL_FUNCTIONS_OUTPUT_BLOB:
        raise ValueError('historical functions output binding changed')
    return without_extended_exception_probes(source.decode('utf-8')).encode('utf-8')


EXCEPTION_CONTEXT_BASE_BLOB = '540d0fa68f212cef2963da7e1e59565a0a56edb6'
EXCEPTION_CONTEXT_PROBE_BLOCKS = (
    ('// Begin exception context checkpoint helpers.\n',
     '// End exception context checkpoint helpers.\n\n'),
    ('// Begin exception context checkpoint observations.\n',
     '// End exception context checkpoint observations.\n'),
)


def without_exception_context_probes(text):
    """Restore the exact 111-record source native-audited on PR88, not its output."""
    if any(boundary in text for pair in EXPORTED_VARIABLE_PROBE_BLOCKS for boundary in pair):
        text = without_exported_variable_probes(text)
    for start, end in EXCEPTION_CONTEXT_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exception context probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != EXCEPTION_CONTEXT_BASE_BLOB:
        raise ValueError('exception context baseline source binding changed')
    return text


EXPORTED_VARIABLE_BASE_BLOB = '6a56f0f5bbca057bbdd9d9f339ab5a0c59d90650'
EXPORTED_VARIABLE_PROBE_BLOCKS = (('// Begin exported variable checkpoint declarations.\n', '// End exported variable checkpoint declarations.\n\n'), ('// Begin exported variable checkpoint helpers.\n', '// End exported variable checkpoint helpers.\n\n'), ('// Begin exported variable checkpoint observations.\n', '// End exported variable checkpoint observations.\n'))

def without_exported_variable_probes(text):
    """Exact prior 116-record source, never a native-output truncation."""
    if any(boundary in text for pair in EXPORTED_CONTEXT_PROBE_BLOCKS for boundary in pair):
        text = without_exported_context_probes(text)
    for start, end in EXPORTED_VARIABLE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exported variable probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != EXPORTED_VARIABLE_BASE_BLOB:
        raise ValueError('exported variable baseline source binding changed')
    return text


EXPORTED_CONTEXT_BASE_BLOB = '0c0cfae158f10fec2343992fbbc7642cd5ced6bc'
EXPORTED_CONTEXT_PROBE_BLOCKS = (
    ('// Begin exported variable discriminator helpers.\n',
     '// End exported variable discriminator helpers.\n\n'),
    ('// Begin exported variable discriminator observations.\n',
     '// End exported variable discriminator observations.\n'),
)


def without_exported_context_probes(text):
    """Restore the complete native-audited PR89 131-record source, not output."""
    if ("NativePostCreate" in text or any(
            boundary in text for pair in EXPORTED_POSTCREATE_PROBE_BLOCKS for boundary in pair)):
        text = without_exported_postcreate_probes(text)
    for start, end in EXPORTED_CONTEXT_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exported context probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    if git_blob(text.encode('utf-8')) != EXPORTED_CONTEXT_BASE_BLOB:
        raise ValueError('exported context baseline source binding changed')
    return text


EXPORTED_POSTCREATE_DIRECTIVE = '// NativePostCreate: ExportProbeAfterCreate\n'
EXPORTED_POSTCREATE_BASE_BLOB = '259abc1315cbcca8642e1a49b44f4ac24a33500e'
EXPORTED_POSTCREATE_BASE_SHA256 = 'c6b33e07818ce7e4abd8153feb3d8538d48737d5a543312b18f1fb8e7c5a65cd'
EXPORTED_POSTCREATE_PROBE_BLOCKS = (
    ('// Begin exported variable post-create declarations.\n',
     '// End exported variable post-create declarations.\n\n'),
    ('// Begin exported variable post-create helpers.\n',
     '// End exported variable post-create helpers.\n\n'),
)


def without_exported_postcreate_probes(text):
    """Restore every byte of the audited 136-record source, never its output."""
    if any(boundary in text for pair in TRAILING_OMITTED_PROBE_BLOCKS for boundary in pair):
        text = without_trailing_omitted_probes(text)
    if not text.startswith(EXPORTED_POSTCREATE_DIRECTIVE) or text.count(EXPORTED_POSTCREATE_DIRECTIVE) != 1:
        raise ValueError('exported post-create directive changed')
    text = text[len(EXPORTED_POSTCREATE_DIRECTIVE):]
    for start, end in EXPORTED_POSTCREATE_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('exported post-create probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if (git_blob(raw) != EXPORTED_POSTCREATE_BASE_BLOB
            or hashlib.sha256(raw).hexdigest() != EXPORTED_POSTCREATE_BASE_SHA256):
        raise ValueError('exported post-create baseline source binding changed')
    return text


# Measurement-only additions to the complete 136-record initialization source.
# This projection is only for historical/checkpoint replay, never live comparison.
TRAILING_OMITTED_BASE_BLOB = '0393cf93cf5380b0231a9b36ce067e3af682d532'
TRAILING_OMITTED_BASE_SHA256 = '21d53297530d86c260b75659f7fdab2e35acddf82e53ab9056f9991a4195a3ab'
TRAILING_OMITTED_SOURCE_SHA256 = 'b1862eb7569e23e054c4abc14711a4faa53b1e26fd16212502317e592caf98a3'
TRAILING_OMITTED_PROBE_BLOCKS = (
    ('// Begin trailing omitted argument checkpoint declarations.\n',
     '// End trailing omitted argument checkpoint declarations.\n\n'),
    ('// Begin trailing omitted argument checkpoint helpers.\n',
     '// End trailing omitted argument checkpoint helpers.\n\n'),
    ('// Begin trailing omitted argument checkpoint observations.\n',
     '// End trailing omitted argument checkpoint observations.\n'),
)


def without_trailing_omitted_probes(text):
    """Restore every byte of the prior source; never trim observed output."""
    if any(boundary in text for boundary in TRAILING_OMITTED_DIRECT_BLOCK):
        text = without_trailing_omitted_direct_probe(text)
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != TRAILING_OMITTED_SOURCE_SHA256:
        raise ValueError('trailing omitted source binding changed')
    for start, end in TRAILING_OMITTED_PROBE_BLOCKS:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('trailing omitted probe boundaries changed')
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before + after
    raw = text.encode('utf-8')
    if (git_blob(raw) != TRAILING_OMITTED_BASE_BLOB
            or hashlib.sha256(raw).hexdigest() != TRAILING_OMITTED_BASE_SHA256):
        raise ValueError('trailing omitted baseline source binding changed')
    return text


# The fresh literal positive witness adds no output and has an exact inverse to
# the independently audited Execute measurement, whose source pin stays intact.
TRAILING_OMITTED_DIRECT_SOURCE_SHA256 = 'b180494a704f59bc959cc07afecb9e568cd0fa64bb73109e45f7ae52b003bfbb'
TRAILING_OMITTED_DIRECT_BLOCK = (
    '    // Begin trailing omitted direct positive witness.\n',
    '    // End trailing omitted direct positive witness.\n',
)


def without_trailing_omitted_direct_probe(text):
    """Restore the complete captured measurement source, not projected output."""
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != TRAILING_OMITTED_DIRECT_SOURCE_SHA256:
        raise ValueError('trailing omitted direct source binding changed')
    start, end = TRAILING_OMITTED_DIRECT_BLOCK
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('trailing omitted direct boundaries changed')
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    result = before + after
    old_note = '// Measurement only: native expected token remains unknown until audited capture.'
    new_note = '// Audited Execute token retained; the direct positive witness requires fresh native validation.'
    if result.count(new_note) != 1:
        raise ValueError('trailing omitted direct observation note changed')
    result = result.replace(new_note, old_note, 1)
    if hashlib.sha256(result.encode('utf-8')).hexdigest() != TRAILING_OMITTED_SOURCE_SHA256:
        raise ValueError('trailing omitted captured source binding changed')
    return result
