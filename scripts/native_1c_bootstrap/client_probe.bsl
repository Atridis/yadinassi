// Fixed managed-form client checkpoint, not six-scenario client parity.
&НаКлиенте
Функция КонтекстПробы()
#Если Клиент Тогда
    Возврат "client";
#Иначе
    ВызватьИсключение "not-client";
#КонецЕсли
КонецФункции

&НаКлиенте
Функция ВычислитьПробу()
    Значения = Новый Массив;
    Значения.Добавить(6 * 7);
    Значения.Добавить(НРег("CLIENT") + "-probe");
    Числа = Новый Массив;
    Числа.Добавить(1);
    Числа.Добавить(2);
    Числа.Добавить(3);
    Сумма = 0;
    Для Каждого Число Из Числа Цикл
        Сумма = Сумма + Число;
    КонецЦикла;
    Значения.Добавить(Числа.Количество());
    Значения.Добавить(Сумма);
    Для Каждого Наблюдение Из DirectiveWitnessValues() Цикл
        Значения.Добавить(Наблюдение);
    КонецЦикла;
    For Each CopybackValue In RunScalarCopybackProbe() Do
        Значения.Добавить(CopybackValue);
    EndDo;
    Возврат Значения;
КонецФункции

&НаКлиенте
Процедура ЗаписатьПробу(Знач Путь, Знач Номер, Знач Фаза, Знач Контекст, Знач Значения)
    Запись = Новый ЗаписьJSON;
    Запись.ОткрытьФайл(Путь);
    ЗаписатьJSON(Запись, Новый Структура("schema,nonce,phase,witness,values",
        1, Номер, Фаза, Контекст, Значения));
    Запись.Закрыть();
КонецПроцедуры

&НаКлиенте
Процедура ПриОткрытии(Отказ)
    Попытка
        Чтение = Новый ЧтениеJSON;
        Чтение.ОткрытьФайл(ПараметрЗапуска);
        Запрос = ПрочитатьJSON(Чтение);
        Чтение.Закрыть();
        Контекст = КонтекстПробы();
        ЗаписатьПробу(Запрос.entered, Запрос.nonce, "entered", Контекст, Новый Массив);
        Попытка
            // Explicit private negative checkpoint: a nonmodal stall, never a dialog test.
            Если Запрос.mode = "stall" Тогда
                Пока Истина Цикл
                КонецЦикла;
            КонецЕсли;
            Значения = ВычислитьПробу();
            ЗаписатьПробу(Запрос.completed, Запрос.nonce, "completed", Контекст, Значения);
        Исключение
            ЗаписатьПробу(Запрос.completed, Запрос.nonce, "error", Контекст, Новый Массив);
        КонецПопытки;
    Исключение
        // Missing/partial evidence fails closed in the external verifier.
    КонецПопытки;
    ЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры

// BEGIN bounded directive witness
&AtServer
Function DirectiveAdd(Val A = 20, Val B = 22)
    Return A + B;
EndFunction

&НаСервере
Функция DirectiveSide()
#Если НаСервере И Не НаКлиенте Тогда
    Возврат "server";
#Иначе
    Возврат "other";
#КонецЕсли
КонецФункции

&AtServer
Function DirectiveNested(Val N)
    If N = 0 Then Return DirectiveSide(); EndIf;
    Return DirectiveNested(N - 1);
EndFunction

&AtServer
Procedure DirectiveRebind(Val X)
    X = 99;
EndProcedure

&AtServer
Procedure DirectiveFail()
    Raise "directive-controlled-failure";
EndProcedure

&AtServer
Function DirectiveScalar(Val X)
    Return X;
EndFunction

&AtClient
Function DirectiveWitnessValues()
    Results = New Array;
    Stage = 1;
    Try
    Stage = 1;
    Results.Add("directive.call.add: " + ValueToStringInternal(DirectiveAdd()));
    Stage = 2;
    Results.Add("directive.preprocessor.server: " + DirectiveSide());
    Stage = 3;
#If AtClient And Not AtServer Then
    Results.Add("directive.preprocessor.client: client");
#Else
    Results.Add("directive.preprocessor.client: other");
#EndIf
    Stage = 4;
    Results.Add("directive.call.nested: " + DirectiveNested(2));
    Stage = 5;
    X = 7;
    DirectiveRebind(X);
    Results.Add("directive.param.val: " + ValueToStringInternal(X));
    Stage = 6;
    Try
        DirectiveFail();
        Results.Add("directive.exception: no-error");
    Except
        Results.Add("directive.exception: " + ValueToStringInternal(
            Find(ErrorDescription(), "directive-controlled-failure") > 0));
    EndTry;
    Stage = 7;
    Results.Add("directive.return.number: " + ValueToStringInternal(DirectiveScalar(42)));
    Stage = 8;
    Results.Add("directive.return.string: " + ValueToStringInternal(DirectiveScalar("x")));
    Stage = 9;
    Results.Add("directive.return.boolean: " + ValueToStringInternal(DirectiveScalar(True)));
    Stage = 10;
    Results.Add("directive.return.undefined: " + ValueToStringInternal(DirectiveScalar(Undefined)));
    Stage = 11;
    Results.Add("directive.call.recovery: " + ValueToStringInternal(DirectiveAdd()));
    Except
        // Fixed stage only: never export native exception descriptions.
        Results = New Array;
        Results.Add("directive.runtime-error");
        Results.Add(Stage);
    EndTry;
    Return Results;
EndFunction

// BEGIN bounded scalar copyback measurement
&AtServer
Procedure CopybackSet(X)
    X = 43;
EndProcedure

&AtServer
Procedure CopybackVal(Val X)
    X = 43;
EndProcedure

&AtServer
Function CopybackFunction(X)
    X = 43;
    Return 97;
EndFunction

&AtServer
Function CopybackCaught(X)
    X = 47;
    Try
        Raise "copyback-core-controlled-failure";
    Except
        Return Find(ErrorDescription(), "copyback-core-controlled-failure") > 0;
    EndTry;
    Return False;
EndFunction

&AtServer
Procedure CopybackEscapes(X, Untouched, Val Control)
    X = 47;
    Control = 99;
    Raise "copyback-core-controlled-failure";
EndProcedure

&AtServer
Function CopybackIndependent(A, B)
    A = 41;
    Return B;
EndFunction

&AtServer
Procedure CopybackRightmost(A, B)
    B = 52;
    A = 41;
EndProcedure

&AtServer
Procedure CopybackUnchangedRight(A, B)
    A = 41;
EndProcedure

&AtServer
Procedure CopybackSelfAssignment(A, B)
    A = 41;
    B = B;
EndProcedure

&AtServer
Procedure CopybackReverted(A, B)
    A = 41;
    B = 2;
    B = 1;
EndProcedure

&AtServer
Function CopybackTiming(Val Before, A, Val After)
    Return Before * 100 + A * 10 + After;
EndFunction

&AtClient
Function CopybackBefore(Calls)
    Calls = Calls + 1;
    Return Calls;
EndFunction

&AtClient
Function CopybackChange(X, Calls)
    Calls = Calls + 1;
    X = 9;
    Return Calls;
EndFunction

&AtClient
Procedure CopybackRecord(Records, Val Label, Val Value)
    Records.Add(ValueToStringInternal(Value));
EndProcedure

&AtClient
Function RunScalarCopybackProbe()
    Var X, Y, Control, Failed, Result, Matched, Caught, Calls;
    Records = New Array;
    Records.Add("copyback.core.v1");
    CopybackRecord(Records, "entered", True);

    X = 1;
    Failed = False;
    Try
        CopybackSet(X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "success.error", Failed);
    CopybackRecord(Records, "success.value", X);

    X = 1;
    Failed = False;
    Try
        CopybackVal(X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "val.error", Failed);
    CopybackRecord(Records, "val.value", X);

    X = 1;
    Result = Undefined;
    Failed = False;
    Try
        Result = CopybackFunction(X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "function.error", Failed);
    CopybackRecord(Records, "function.result", Result);
    CopybackRecord(Records, "function.value", X);

    X = 1;
    Matched = False;
    Failed = False;
    Try
        Matched = CopybackCaught(X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "caught.error", Failed);
    CopybackRecord(Records, "caught.matched", Matched);
    CopybackRecord(Records, "caught.value", X);

    X = 1;
    Y = 2;
    Control = 3;
    Caught = False;
    Matched = False;
    Try
        CopybackEscapes(X, Y, Control);
    Except
        Caught = True;
        Matched = Find(ErrorDescription(), "copyback-core-controlled-failure") > 0;
    EndTry;
    CopybackRecord(Records, "escaped.caught", Caught);
    CopybackRecord(Records, "escaped.matched", Matched);
    CopybackRecord(Records, "escaped.value", X);
    CopybackRecord(Records, "escaped.untouched", Y);
    CopybackRecord(Records, "escaped.val", Control);

    X = 1;
    Result = Undefined;
    Failed = False;
    Try
        Result = CopybackIndependent(X, X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "alias.independent.error", Failed);
    CopybackRecord(Records, "alias.independent.second", Result);
    CopybackRecord(Records, "alias.independent.value", X);

    X = 1;
    Failed = False;
    Try
        CopybackRightmost(X, X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "alias.rightmost.error", Failed);
    CopybackRecord(Records, "alias.rightmost.value", X);

    X = 1;
    Failed = False;
    Try
        CopybackUnchangedRight(X, X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "alias.unchanged-right.error", Failed);
    CopybackRecord(Records, "alias.unchanged-right.value", X);

    X = 1;
    Failed = False;
    Try
        CopybackSelfAssignment(X, X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "alias.self-assignment.error", Failed);
    CopybackRecord(Records, "alias.self-assignment.value", X);

    X = 1;
    Failed = False;
    Try
        CopybackReverted(X, X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "alias.reverted.error", Failed);
    CopybackRecord(Records, "alias.reverted.value", X);

    X = 1;
    Calls = 0;
    Result = Undefined;
    Failed = False;
    Try
        Result = CopybackTiming(CopybackBefore(Calls), X, CopybackChange(X, Calls));
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "timing.error", Failed);
    CopybackRecord(Records, "timing.signature", Result);
    CopybackRecord(Records, "timing.value", X);
    CopybackRecord(Records, "timing.calls", Calls);

    X = 1;
    Failed = False;
    Try
        CopybackSet(X);
    Except
        Failed = True;
    EndTry;
    CopybackRecord(Records, "recovery.error", Failed);
    CopybackRecord(Records, "recovery.value", X);
    CopybackRecord(Records, "complete", True);
    Return Records;
EndFunction
