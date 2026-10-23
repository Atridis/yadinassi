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
    For Each ObjectTransferValue In RunObjectTransferProbe() Do
        Значения.Добавить(ObjectTransferValue);
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

// BEGIN bounded object transfer measurement
&AtServer
Procedure ObjectTransferVal(Val P)
    P.N = 11;
    P.Items[0] = 12;
    P = New Structure("N", 13);
EndProcedure

&AtServer
Function ObjectTransferIndependent(A, B)
    Var Seen;
    A.Items[0] = 21;
    Seen = B.Items[0];
    B.Items[0] = 23;
    Return Seen;
EndFunction

&AtServer
Function ObjectTransferRepeated(A, B)
    A.Items[0] = 31;
    Return B.Items[0];
EndFunction

&AtServer
Procedure ObjectTransferRebind(P)
    Var Items;
    Items = New Array;
    Items.Add(42);
    P = New Structure("N,Items", 41, Items);
EndProcedure

&AtServer
Function ObjectTransferGraph(P, Seen)
    P.Left[0] = 51;
    Seen = P.Right[0];
    // Recreate sharing explicitly so outgoing behavior is independent of input.
    P.Right = P.Left;
    Return P;
EndFunction

&AtServer
Procedure ObjectTransferEscapes(P, Untouched, Val Control)
    Var Items;
    P.N = 61;
    P.Items[0] = 62;
    Control.N = 63;
    Control.Items[0] = 64;
    Items = New Array;
    Items.Add(66);
    P = New Structure("N,Items", 65, Items);
    Raise "object-transfer-core-controlled-failure";
EndProcedure

&AtServer
Function ObjectTransferTiming(Val Early, Late, Val Token)
    Return New Structure("Early,Late", Early.Items[0], Late.Items[0]);
EndFunction

&AtServer
Function ObjectTransferCaught(P)
    P.N = 81;
    P.Items[0] = 82;
    Try
        Raise "object-transfer-core-controlled-failure";
    Except
        Return Find(ErrorDescription(), "object-transfer-core-controlled-failure") > 0;
    EndTry;
    Return False;
EndFunction

&AtClient
Function ObjectTransferNew(Val N)
    Var Items;
    Items = New Array;
    Items.Add(N);
    Return New Structure("N,Items", N, Items);
EndFunction

&AtClient
Function ObjectTransferChange(X, Calls)
    Calls = Calls + 1;
    X.N = 71;
    X.Items[0] = 72;
    X = ObjectTransferNew(73);
    Return 74;
EndFunction

&AtClient
Function ObjectTransferNumber(Val Value)
    If TypeOf(Value) <> Type("Number") Then
        Return Undefined;
    EndIf;
    If Value < 0 Or Value >= 1000 Then
        Return Undefined;
    EndIf;
    Return Value;
EndFunction

&AtClient
Function ObjectTransferField(Val Value, Val Key)
    Var Item;
    If TypeOf(Value) <> Type("Structure") Then
        Return Undefined;
    EndIf;
    Item = Undefined;
    If Not Value.Property(Key, Item) Then
        Return Undefined;
    EndIf;
    Return ObjectTransferNumber(Item);
EndFunction

&AtClient
Function ObjectTransferArrayLeaf(Val Value)
    If TypeOf(Value) <> Type("Array") Then
        Return Undefined;
    EndIf;
    If Value.Count() = 0 Then
        Return Undefined;
    EndIf;
    Return ObjectTransferNumber(Value[0]);
EndFunction

&AtClient
Function ObjectTransferLeaf(Val Value, Val Key)
    Var Item;
    If TypeOf(Value) <> Type("Structure") Then
        Return Undefined;
    EndIf;
    Item = Undefined;
    If Not Value.Property(Key, Item) Then
        Return Undefined;
    EndIf;
    Return ObjectTransferArrayLeaf(Item);
EndFunction

&AtClient
Procedure ObjectTransferRecord(Records, Val Label, Val Value)
    // The future integrated adapter replaces this one sink with Records.Add.
    // The value is always Number, Boolean or Undefined, never an object/error.
    If Value = Undefined Then
        Records.Add("U");
    Else
        Records.Add(Value);
    EndIf;
EndProcedure

&AtServer
Function ObjectTransferMixedTiming(Val NamedObject, Val AliasObject, Val ExpressionObject, Val NamedScalar, Val ExpressionScalar, Val Token)
    Return New Structure("NamedObject,AliasObject,ExpressionObject,NamedScalar,ExpressionScalar", NamedObject.Items[0], AliasObject.Items[0], ExpressionObject.Items[0], NamedScalar, ExpressionScalar);
EndFunction

&AtClient
Function ObjectTransferIdentity(Val Value)
    Return Value;
EndFunction

&AtClient
Function ObjectTransferChangeBoth(X, Scalar, Calls)
    Calls = Calls + 1;
    X.Items[0] = 72;
    X = ObjectTransferNew(73);
    Scalar = 74;
    Return 75;
EndFunction

&AtClient
Function RunObjectTransferProbe()
    Var Records, ObjectStage;
    Var Scalar;
    Var X, Y, Kept, Child, Control, Untouched, Result, Seen, Calls;
    Var Failed, Matched, BeforeX, BeforeY, AfterY;
    Var AfterXSibling, AfterXResultLeft, AfterXResultRight;
    Var AfterResultSibling, AfterResultXLeft, AfterResultXRight;

    Records = New Array;
    Records.Add("object.transfer.v1");
    ObjectStage = 0;
    Try
        ObjectStage = 1;
        ObjectTransferRecord(Records, "entered", True);
    
        // 1. Val: nested mutation followed by formal rebinding.
        ObjectStage = 2;
        X = ObjectTransferNew(1);
        ObjectStage = 3;
        Child = X.Items;
        ObjectStage = 4;
        Failed = False;
        Try
        ObjectStage = 5;
            ObjectTransferVal(X);
        Except
        ObjectStage = 6;
            Failed = True;
        EndTry;
        ObjectStage = 7;
        ObjectTransferRecord(Records, "val.error", Failed);
        ObjectStage = 8;
        ObjectTransferRecord(Records, "val.root", ObjectTransferField(X, "N"));
        ObjectStage = 9;
        ObjectTransferRecord(Records, "val.leaf", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 10;
        ObjectTransferRecord(Records, "val.retained", ObjectTransferArrayLeaf(Child));
    
        // 2. Two different caller variables initially alias the same object.
        ObjectStage = 11;
        X = ObjectTransferNew(2);
        ObjectStage = 12;
        Y = X;
        ObjectStage = 13;
        Child = X.Items;
        ObjectStage = 14;
        Seen = Undefined;
        ObjectStage = 15;
        BeforeX = Undefined;
        ObjectStage = 16;
        BeforeY = Undefined;
        ObjectStage = 17;
        AfterY = Undefined;
        ObjectStage = 18;
        Failed = False;
        Try
        ObjectStage = 19;
            Seen = ObjectTransferIndependent(X, Y);
        ObjectStage = 20;
            BeforeX = ObjectTransferLeaf(X, "Items");
        ObjectStage = 21;
            BeforeY = ObjectTransferLeaf(Y, "Items");
        ObjectStage = 22;
            X.Items[0] = 24;
        ObjectStage = 23;
            AfterY = ObjectTransferLeaf(Y, "Items");
        Except
        ObjectStage = 24;
            Failed = True;
        EndTry;
        ObjectStage = 25;
        ObjectTransferRecord(Records, "independent.error", Failed);
        ObjectStage = 26;
        ObjectTransferRecord(Records, "independent.server.second", ObjectTransferNumber(Seen));
        ObjectStage = 27;
        ObjectTransferRecord(Records, "independent.x.before", BeforeX);
        ObjectStage = 28;
        ObjectTransferRecord(Records, "independent.y.before", BeforeY);
        ObjectStage = 29;
        ObjectTransferRecord(Records, "independent.y.after", AfterY);
        ObjectStage = 30;
        ObjectTransferRecord(Records, "independent.retained", ObjectTransferArrayLeaf(Child));
    
        // 3. One caller sink repeated; rightmost formal is not mutated or rebound.
        ObjectStage = 31;
        X = ObjectTransferNew(3);
        ObjectStage = 32;
        Child = X.Items;
        ObjectStage = 33;
        Seen = Undefined;
        ObjectStage = 34;
        Failed = False;
        Try
        ObjectStage = 35;
            Seen = ObjectTransferRepeated(X, X);
        Except
        ObjectStage = 36;
            Failed = True;
        EndTry;
        ObjectStage = 37;
        ObjectTransferRecord(Records, "repeated.error", Failed);
        ObjectStage = 38;
        ObjectTransferRecord(Records, "repeated.server.second", ObjectTransferNumber(Seen));
        ObjectStage = 39;
        ObjectTransferRecord(Records, "repeated.leaf", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 40;
        ObjectTransferRecord(Records, "repeated.retained", ObjectTransferArrayLeaf(Child));
    
        // 4. Explicit non-Val root replacement, with an unpassed old root alias.
        ObjectStage = 41;
        X = ObjectTransferNew(4);
        ObjectStage = 42;
        Kept = X;
        ObjectStage = 43;
        Failed = False;
        Try
        ObjectStage = 44;
            ObjectTransferRebind(X);
        Except
        ObjectStage = 45;
            Failed = True;
        EndTry;
        ObjectStage = 46;
        ObjectTransferRecord(Records, "rebind.error", Failed);
        ObjectStage = 47;
        ObjectTransferRecord(Records, "rebind.root", ObjectTransferField(X, "N"));
        ObjectStage = 48;
        ObjectTransferRecord(Records, "rebind.leaf", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 49;
        ObjectTransferRecord(Records, "rebind.retained", ObjectTransferField(Kept, "N"));
    
        // 5. Shared child on input; explicit server sharing on output and return.
        ObjectStage = 50;
        Child = New Array;
        ObjectStage = 51;
        Child.Add(5);
        ObjectStage = 52;
        X = New Structure("Left,Right", Child, Child);
        ObjectStage = 53;
        Seen = Undefined;
        ObjectStage = 54;
        Result = Undefined;
        ObjectStage = 55;
        AfterXSibling = Undefined;
        ObjectStage = 56;
        AfterXResultLeft = Undefined;
        ObjectStage = 57;
        AfterXResultRight = Undefined;
        ObjectStage = 58;
        AfterResultSibling = Undefined;
        ObjectStage = 59;
        AfterResultXLeft = Undefined;
        ObjectStage = 60;
        AfterResultXRight = Undefined;
        ObjectStage = 61;
        Failed = False;
        Try
        ObjectStage = 62;
            Result = ObjectTransferGraph(X, Seen);
        ObjectStage = 63;
            X.Left[0] = 52;
        ObjectStage = 64;
            AfterXSibling = ObjectTransferLeaf(X, "Right");
        ObjectStage = 65;
            AfterXResultLeft = ObjectTransferLeaf(Result, "Left");
        ObjectStage = 66;
            AfterXResultRight = ObjectTransferLeaf(Result, "Right");
        ObjectStage = 67;
            Result.Left[0] = 53;
        ObjectStage = 68;
            AfterResultSibling = ObjectTransferLeaf(Result, "Right");
        ObjectStage = 69;
            AfterResultXLeft = ObjectTransferLeaf(X, "Left");
        ObjectStage = 70;
            AfterResultXRight = ObjectTransferLeaf(X, "Right");
        Except
        ObjectStage = 71;
            Failed = True;
        EndTry;
        ObjectStage = 72;
        ObjectTransferRecord(Records, "graph.error", Failed);
        ObjectStage = 73;
        ObjectTransferRecord(Records, "graph.server.sibling", ObjectTransferNumber(Seen));
        ObjectStage = 74;
        ObjectTransferRecord(Records, "graph.x.sibling", AfterXSibling);
        ObjectStage = 75;
        ObjectTransferRecord(Records, "graph.result.left.after.x", AfterXResultLeft);
        ObjectStage = 76;
        ObjectTransferRecord(Records, "graph.result.right.after.x", AfterXResultRight);
        ObjectStage = 77;
        ObjectTransferRecord(Records, "graph.result.sibling", AfterResultSibling);
        ObjectStage = 78;
        ObjectTransferRecord(Records, "graph.x.left.after.result", AfterResultXLeft);
        ObjectStage = 79;
        ObjectTransferRecord(Records, "graph.x.right.after.result", AfterResultXRight);
        ObjectStage = 80;
        ObjectTransferRecord(Records, "graph.retained", ObjectTransferArrayLeaf(Child));
    
        // 6. Escaping server failure. Readers handle Undefined before dereferencing.
        ObjectStage = 81;
        X = ObjectTransferNew(6);
        ObjectStage = 82;
        Kept = X;
        ObjectStage = 83;
        Child = X.Items;
        ObjectStage = 84;
        Untouched = ObjectTransferNew(7);
        ObjectStage = 85;
        Control = ObjectTransferNew(8);
        ObjectStage = 86;
        Failed = False;
        ObjectStage = 87;
        Matched = False;
        Try
        ObjectStage = 88;
            ObjectTransferEscapes(X, Untouched, Control);
        Except
        ObjectStage = 89;
            Failed = True;
        ObjectStage = 90;
            Matched = Find(ErrorDescription(), "object-transfer-core-controlled-failure") > 0;
        EndTry;
        ObjectStage = 91;
        ObjectTransferRecord(Records, "escaped.error", Failed);
        ObjectStage = 92;
        ObjectTransferRecord(Records, "escaped.matched", Matched);
        ObjectStage = 93;
        ObjectTransferRecord(Records, "escaped.value.undefined", X = Undefined);
        ObjectStage = 94;
        ObjectTransferRecord(Records, "escaped.value.leaf", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 95;
        ObjectTransferRecord(Records, "escaped.retained.root", ObjectTransferField(Kept, "N"));
        ObjectStage = 96;
        ObjectTransferRecord(Records, "escaped.retained.leaf", ObjectTransferArrayLeaf(Child));
        ObjectStage = 97;
        ObjectTransferRecord(Records, "escaped.untouched.undefined", Untouched = Undefined);
        ObjectStage = 98;
        ObjectTransferRecord(Records, "escaped.untouched.leaf", ObjectTransferLeaf(Untouched, "Items"));
        ObjectStage = 99;
        ObjectTransferRecord(Records, "escaped.val.leaf", ObjectTransferLeaf(Control, "Items"));
    
        // 7. Earlier Val object handle versus later mutation and rebinding of X.
        ObjectStage = 100;
        X = ObjectTransferNew(9);
        ObjectStage = 101;
        Child = X.Items;
        ObjectStage = 102;
        Calls = 0;
        ObjectStage = 103;
        Result = Undefined;
        ObjectStage = 104;
        Failed = False;
        Try
        ObjectStage = 105;
            Result = ObjectTransferTiming(X, X, ObjectTransferChange(X, Calls));
        Except
        ObjectStage = 106;
            Failed = True;
        EndTry;
        ObjectStage = 107;
        ObjectTransferRecord(Records, "timing.error", Failed);
        ObjectStage = 108;
        ObjectTransferRecord(Records, "timing.early", ObjectTransferField(Result, "Early"));
        ObjectStage = 109;
        ObjectTransferRecord(Records, "timing.late", ObjectTransferField(Result, "Late"));
        ObjectStage = 110;
        ObjectTransferRecord(Records, "timing.caller", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 111;
        ObjectTransferRecord(Records, "timing.retained", ObjectTransferArrayLeaf(Child));
        ObjectStage = 112;
        ObjectTransferRecord(Records, "timing.calls", ObjectTransferNumber(Calls));
    
        // 8. A server-caught error returns normally; also checks post-failure recovery.
        ObjectStage = 113;
        X = ObjectTransferNew(10);
        ObjectStage = 114;
        Child = X.Items;
        ObjectStage = 115;
        Matched = Undefined;
        ObjectStage = 116;
        Failed = False;
        Try
        ObjectStage = 117;
            Matched = ObjectTransferCaught(X);
        Except
        ObjectStage = 118;
            Failed = True;
        EndTry;
        ObjectStage = 119;
        ObjectTransferRecord(Records, "recovery.error", Failed);
        ObjectStage = 120;
        ObjectTransferRecord(Records, "recovery.matched", Matched);
        ObjectStage = 121;
        ObjectTransferRecord(Records, "recovery.leaf", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 122;
        ObjectTransferRecord(Records, "recovery.retained", ObjectTransferArrayLeaf(Child));
    
        ObjectStage = 123;
        ObjectTransferRecord(Records, "complete", True);
    
        // 9. Named storage versus expression results before a later argument effect.
        ObjectStage = 124;
        X = ObjectTransferNew(9);
        ObjectStage = 125;
        Kept = X;
        ObjectStage = 126;
        Scalar = 11;
        ObjectStage = 127;
        Calls = 0;
        ObjectStage = 128;
        Result = Undefined;
        ObjectStage = 129;
        Failed = False;
        Try
        ObjectStage = 130;
            Result = ObjectTransferMixedTiming(X, Kept, ObjectTransferIdentity(X), Scalar, ObjectTransferIdentity(Scalar), ObjectTransferChangeBoth(X, Scalar, Calls));
        Except
        ObjectStage = 131;
            Failed = True;
        EndTry;
        ObjectStage = 132;
        ObjectTransferRecord(Records, "mixed.error", Failed);
        ObjectStage = 133;
        ObjectTransferRecord(Records, "mixed.named.object", ObjectTransferField(Result, "NamedObject"));
        ObjectStage = 134;
        ObjectTransferRecord(Records, "mixed.alias.object", ObjectTransferField(Result, "AliasObject"));
        ObjectStage = 135;
        ObjectTransferRecord(Records, "mixed.expression.object", ObjectTransferField(Result, "ExpressionObject"));
        ObjectStage = 136;
        ObjectTransferRecord(Records, "mixed.named.scalar", ObjectTransferField(Result, "NamedScalar"));
        ObjectStage = 137;
        ObjectTransferRecord(Records, "mixed.expression.scalar", ObjectTransferField(Result, "ExpressionScalar"));
        ObjectStage = 138;
        ObjectTransferRecord(Records, "mixed.caller.object", ObjectTransferLeaf(X, "Items"));
        ObjectStage = 139;
        ObjectTransferRecord(Records, "mixed.caller.scalar", ObjectTransferNumber(Scalar));
        ObjectStage = 140;
        ObjectTransferRecord(Records, "mixed.retained", ObjectTransferLeaf(Kept, "Items"));
        ObjectStage = 141;
        ObjectTransferRecord(Records, "mixed.calls", ObjectTransferNumber(Calls));
    Except
        Records = New Array;
        Records.Add("object.runtime-error");
        Records.Add(ObjectStage);
    EndTry;
    Return Records;
EndFunction
