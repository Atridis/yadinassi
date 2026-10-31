"""One authenticated session per context; eight independently bounded outputs."""
import re
from catalog_read_fixture import BLOCKS, STATES
from inject_metadata import bsl_string


def once(text, before, after):
    if text.count(before) != 1: raise ValueError('catalog-read-anchor')
    return text.replace(before, after)


def wrap(raw, name):
    text = raw.decode('utf-8-sig').replace('\r\n', '\n')
    head, body = text.split('Сообщить("CR-C1:', 1)
    body = 'Сообщить("CR-C1:' + body
    # Catalogs may be absent from a client compilation context. Resolve only
    # direct Catalogs action expressions dynamically in THIS function scope;
    # cursor variables stay local and scalar calibration still runs on failure.
    # Trusted source only, never a caller expression. Server-only setup is direct.
    if name.startswith('B'):
        pattern = r'\b(Result|S|FreshA|FreshB) = ([^;\n]*Catalogs[^;\n]*);'
        body = re.sub(pattern, lambda m:m[1]+' = Вычислить('+bsl_string(m[2])+');', body)
        body = re.sub(r'^(\s*)(Catalogs\.[^\n]+;)$',
            lambda m:m[1]+'Выполнить('+bsl_string(m[2])+');',body,flags=re.M)
    # Explicit output accumulator parameters, not module globals.
    text = head + 'Функция CRRun()\nLines = Новый Массив;\n' + body
    text += '\nВозврат СтрСоединить(Lines, Символ(10)) + Символ(10);\nКонецФункции\n'
    if name.startswith('S'):
        # Fixed source-owned breadcrumbs only; no exception text or caller data.
        text = text.replace('CRRun()', 'CRRun(Diagnostic)')
        text = text.replace('CRCount(', 'CRCount(Diagnostic, ')
        text = text.replace('    Q = Новый Запрос;', '    Diagnostic.phase = "setup-query-build";\n    Q = Новый Запрос;')
        text = text.replace('    Row = Q.Выполнить().Выбрать();', '    Diagnostic.phase = "setup-query-execute";\n    Row = Q.Выполнить().Выбрать();')
        text = text.replace('    Если Не Row.Следующий()', '    Diagnostic.phase = "setup-query-row";\n    Если Не Row.Следующий()')
        lines = []
        for line in text.splitlines():
            phase = None
            if line.startswith('Сообщить("CR-C1:'): phase = 'setup-calibration-one'
            elif line.startswith('Сообщить("CR-C2:'): phase = 'setup-calibration-two'
            elif line.startswith('Manager = '): phase = 'setup-manager'
            elif line.startswith('CREmit("'): phase = 'setup-witness-' + line.split('"')[1]
            elif line.startswith(('Object = ', 'Ghost = ', 'Object.', 'Ghost.')): phase = 'setup-mutate'
            if phase is not None: lines.append('Diagnostic.phase = "' + phase + '";')
            lines.append(line)
        text = '\n'.join(lines) + '\n'
    text = text.replace('CREmit(', 'CREmit(Lines, ').replace('CRObserve(', 'CRObserve(Lines, ')
    text = text.replace('Сообщить(', 'Lines.Добавить(')
    return re.sub(r'\b(CRText|CRScalar|CREmit|CRObserve|CRCount|CRRun)\b', lambda m:name + m[0], text)


SERVER = '''
Функция CBSelected(Token) Экспорт
    Control = NativeПрочитатьJSON(@@EVIDENCE@@ + "/control.json");
    Если ТипЗнч(Control) <> Тип("Структура") Тогда ВызватьИсключение "invalid_control"; КонецЕсли;
    Если Control.Количество() <> 4 Или ТипЗнч(Control.schema) <> Тип("Число") Или Control.schema <> 1
        Или Control.nonce <> @@NONCE@@ Или Control.token <> Token Тогда ВызватьИсключение "invalid_control"; КонецЕсли;
    Возврат СтрНайти(",catalog_read_client,catalog_read_server,catalog_read_setup_empty,catalog_read_setup_one,catalog_read_setup_several,catalog_read_setup_deleted,catalog_read_setup_reused,", "," + Control.operation + ",") > 0;
КонецФункции
Функция CBAuthorized(Token) Экспорт
    Если Не CBSelected(Token) Тогда ВызватьИсключение "invalid_control"; КонецЕсли;
    Control = NativeПрочитатьJSON(@@EVIDENCE@@ + "/control.json");
    Response = Новый Структура("operation,outputs,status,phase", Control.operation, Новый Структура, "error", "identity");
    Попытка
        Если ПривилегированныйРежим() Тогда ВызватьИсключение "permission_mismatch"; КонецЕсли;
        Current = ПользователиИнформационнойБазы.ТекущийПользователь();
        NativeПроверитьПользователя(Current, @@CRUD_USER@@, Метаданные.Роли.NativeOracleCatalogCRUD);
        Если Current.Роли.Содержит(Метаданные.Роли.NativeOracleSetupAdministrator)
            Или ПравоДоступа("Администрирование", Метаданные)
            Или ПравоДоступа("АдминистрированиеДанных", Метаданные) Тогда
            ВызватьИсключение "permission_mismatch";
        КонецЕсли;
        // The separate existing admin audit verifies the complete user list.
        // Never enumerate it from this nonprivileged CRUD identity.
        Response.phase = "metadata";
        Result = NativeНовыйРезультат(Control);
        NativeПроверитьМетаданные(Result);
        Output = Новый Структура;
        Response.phase = "observe";
        Если Control.operation = "catalog_read_server" Тогда Output = CBAll(); КонецЕсли;
        Response.phase = "setup";
        @@SETUP_DISPATCH@@
        Response.outputs = Output;
        Response.status = "ok";
        Response.phase = "complete";
    Исключение
        // Only a fixed phase is returned; never exception text or partial data.
    КонецПопытки;
    Возврат Response;
КонецФункции
'''
CLIENT = '''
Процедура CBDispatch(Token)
    Operation = "catalog_read_client";
    Completion = Новый Структура("schema,nonce,token,operation,phase,status", 1, @@NONCE@@, Token, Operation, "authorize", "error");
    Попытка
        Response = NativeOracleServer.CBAuthorized(Token);
        Operation = Response.operation;
        Completion.operation = Operation;
        Completion.phase = Response.phase;
        Если Response.status <> "ok" Тогда
            NativeЗаписатьЗавершение(Completion);
            Возврат;
        КонецЕсли;
        Completion.phase = "observe";
        Outputs = Response.outputs;
        Если Operation = "catalog_read_client" Тогда Outputs = CBAll(); КонецЕсли;
        Completion.phase = "serialize";
        Result = Новый Структура("schema,nonce,token,operation,status,outputs", 1, @@NONCE@@, Token, Operation, "ok", Outputs);
        Target = Новый Файл(@@EVIDENCE@@ + "/result.json");
        Если Target.Существует() Тогда ВызватьИсключение "stale_evidence"; КонецЕсли;
        Writer = Новый ЗаписьJSON;
        Writer.ОткрытьФайл(Target.ПолноеИмя);
        ЗаписатьJSON(Writer, Result);
        Writer.Закрыть();
        Completion.phase = "complete";
        Completion.status = "ok";
    Исключение
        // Preserve failure; never serialize native error text.
    КонецПопытки;
    NativeЗаписатьЗавершение(Completion);
КонецПроцедуры
'''


def instrument(raw, name, b, files, *, nonce, evidence):
    text = raw.decode('utf-8-sig').replace('\r\n', '\n')
    if 'CBSelected' in text or 'CBDispatch' in text: raise ValueError('already-instrumented')
    blocks = ''.join(wrap(files[block + '.bsl'], 'B' + str(i)) for i, block in enumerate(BLOCKS))
    all_function = 'Функция CBAll()\nOutputs = Новый Структура;\n'
    for i, block in enumerate(BLOCKS):
        all_function += f'Outputs.Вставить("{block}", B{i}CRRun());\n'
    all_function += 'Возврат Outputs;\nКонецФункции\n'
    if name == 'NativeOracleServer.bsl':
        text = once(text, 'Метаданные.Справочники.Количество() <> 1', 'Метаданные.Справочники.Количество() <> 3')
        for catalog in b.setup.names:
            guard = f'''Каталог = Метаданные.Справочники.{catalog};
    Если Каталог.ДлинаКода <> 2 Или Каталог.ДлинаНаименования <> 8 Или Каталог.Иерархический
        Или Каталог.Реквизиты.Количество() <> 2 Или Каталог.ТабличныеЧасти.Количество() <> 0 Тогда ВызватьИсключение "metadata_mismatch"; КонецЕсли;
    '''
            text = once(text, '    Каталог = Метаданные.Справочники.NativeOracleItems;', '    ' + guard + 'Каталог = Метаданные.Справочники.NativeOracleItems;')
        dispatch = ''
        for i, state in enumerate(STATES):
            blocks += wrap(files['setup-' + state + '.bsl'], 'S' + str(i))
            dispatch += f'Если Control.operation = "catalog_read_setup_{state}" Тогда Output.Вставить("setup", S{i}CRRun(Response)); КонецЕсли;\n'
        text += SERVER.replace('@@SETUP_DISPATCH@@', dispatch)
    elif name == 'ManagedApplicationModule.bsl':
        text = once(text, '        Завершение = Новый Структура(', '''        Если NativeOracleServer.CBSelected(ПараметрЗапуска) Тогда
            CBDispatch(ПараметрЗапуска);
            ЗавершитьРаботуСистемы(Ложь);
            Возврат;
        КонецЕсли;
        Завершение = Новый Структура(''')
        text += CLIENT
    else: raise ValueError('module-name')
    text += blocks + all_function
    for key, value in {'NONCE':nonce, 'EVIDENCE':str(evidence), 'SETUP_USER':'NativeOracleSetup', 'CRUD_USER':'NativeOracleCRUD'}.items():
        text = text.replace('@@' + key + '@@', bsl_string(value))
    if '@@' in text: raise ValueError('unexpanded')
    return text.encode('utf-8-sig')
