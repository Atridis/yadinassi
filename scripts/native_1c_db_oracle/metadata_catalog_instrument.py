"""Exact opt-in transformation of trusted owned modules; never caller BSL."""
from pathlib import Path


def _once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('metadata probe anchor')
    return text.replace(before, after)


def observer(source):
    text = source.decode('utf-8-sig').replace('\r\n', '\n')
    text = _once(text, 'Процедура MCEmit(Знач Label, Знач Value)',
                 'Процедура MCEmit(Знач Label, Знач Value, Lines)')
    text = _once(text, 'Процедура MCObserve(Знач Label, Знач Expression)',
                 'Процедура MCObserve(Знач Label, Знач Expression, Lines)')
    text = _once(text, '    MCEmit(Label, Value);', '    MCEmit(Label, Value, Lines);')
    head, body = text.split('Сообщить("MC-C1:', 1)
    body = 'Сообщить("MC-C1:' + body
    import re
    body = re.sub(r'^(MCObserve\(.*)\);', r'\1, Lines);', body, flags=re.M)
    body = _once(body, 'MCEmit("25", Истина);', 'MCEmit("25", Истина, Lines);')
    text = head + 'Функция MCRun()\n    Lines = Новый Массив;\n' + body
    text = text.replace('Сообщить(', 'Lines.Добавить(')
    text += '\n    Возврат СтрСоединить(Lines, Символ(10)) + Символ(10);\nКонецФункции\n'
    return text


SERVER = '''
Функция MCSelected(Token) Экспорт
    Control = NativeПрочитатьJSON(@@EVIDENCE@@ + "/control.json");
    Если ТипЗнч(Control) <> Тип("Структура") Тогда ВызватьИсключение "invalid_control"; КонецЕсли;
    Если Control.Количество() <> 4 Или ТипЗнч(Control.schema) <> Тип("Число") Или Control.schema <> 1
        Или Control.nonce <> @@NONCE@@ Или Control.token <> Token Тогда ВызватьИсключение "invalid_control"; КонецЕсли;
    Возврат Control.operation = "metadata_catalog_client" Или Control.operation = "metadata_catalog_server";
КонецФункции
Функция MCAuthorized(Token) Экспорт
    Если Не MCSelected(Token) Или ПривилегированныйРежим() Тогда ВызватьИсключение "invalid_control"; КонецЕсли;
    Control = NativeПрочитатьJSON(@@EVIDENCE@@ + "/control.json");
    NativeПроверитьПользователя(ПользователиИнформационнойБазы.ТекущийПользователь(), @@SETUP_USER@@, Метаданные.Роли.NativeOracleSetupAdministrator);
    NativeПроверитьВсехПользователей();
    Result = NativeНовыйРезультат(Control);
    NativeПроверитьМетаданные(Result);
    Output = "";
    Если Control.operation = "metadata_catalog_server" Тогда Output = MCRun(); КонецЕсли;
    Возврат Новый Структура("operation,output", Control.operation, Output);
КонецФункции
'''
CLIENT = '''
Процедура MCDispatch(Token)
    Operation = "metadata_catalog_client";
    Completion = Новый Структура("schema,nonce,token,operation,phase,status", 1, @@NONCE@@, Token, Operation, "probe", "error");
    Попытка
        Response = NativeOracleServer.MCAuthorized(Token);
        Operation = Response.operation;
        Completion.operation = Operation;
        Если Operation = "metadata_catalog_client" Тогда
            Output = MCRun();
        ИначеЕсли Operation = "metadata_catalog_server" Тогда
            Output = Response.output;
        Иначе
            ВызватьИсключение "invalid_control";
        КонецЕсли;
        Result = Новый Структура("schema,nonce,token,operation,status,output", 1, @@NONCE@@, Token, Operation, "ok", Output);
        Target = Новый Файл(@@EVIDENCE@@ + "/result.json");
        Если Target.Существует() Тогда ВызватьИсключение "stale_evidence"; КонецЕсли;
        Writer = Новый ЗаписьJSON;
        Writer.ОткрытьФайл(Target.ПолноеИмя);
        ЗаписатьJSON(Writer, Result);
        Writer.Закрыть();
        Completion.phase = "complete";
        Completion.status = "ok";
    Исключение
        // No exception text leaves the process. Partial result is not success.
    КонецПопытки;
    NativeЗаписатьЗавершение(Completion);
КонецПроцедуры
'''


def instrument(source, *, name, probe):
    text = source.decode('utf-8-sig').replace('\r\n', '\n')
    if 'Функция MCSelected(' in text or 'Процедура MCDispatch(' in text:
        raise ValueError('metadata already instrumented')
    if name == 'NativeOracleServer.bsl':
        return (text + SERVER + observer(probe)).encode('utf-8')
    if name == 'ManagedApplicationModule.bsl':
        anchor = '        Завершение = Новый Структура('
        if text.count(anchor) != 1: raise ValueError('metadata dispatch anchor')
        hook = '''        Если NativeOracleServer.MCSelected(ПараметрЗапуска) Тогда
            MCDispatch(ПараметрЗапуска);
            ЗавершитьРаботуСистемы(Ложь);
            Возврат;
        КонецЕсли;
'''
        text = text.replace(anchor, hook + anchor)
        return (text + CLIENT + observer(probe)).encode('utf-8')
    raise ValueError('metadata module selection')
