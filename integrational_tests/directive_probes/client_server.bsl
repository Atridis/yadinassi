// Standalone managed-form module probe. Invoke RunDirectiveProbe on the client.
// Not Execute(text). No database access, asynchronous methods or UI calls.
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
Procedure RunDirectiveProbe() Export
    Message("directive.call.add: " + ValueToStringInternal(DirectiveAdd()));
    Message("directive.preprocessor.server: " + DirectiveSide());
#If AtClient And Not AtServer Then
    Message("directive.preprocessor.client: client");
#Else
    Message("directive.preprocessor.client: other");
#EndIf
    Message("directive.call.nested: " + DirectiveNested(2));
    X = 7;
    DirectiveRebind(X);
    Message("directive.param.val: " + ValueToStringInternal(X));
    Try
        DirectiveFail();
        Message("directive.exception: no-error");
    Except
        Message("directive.exception: " + ValueToStringInternal(
            Find(ErrorDescription(), "directive-controlled-failure") > 0));
    EndTry;
    Message("directive.return.number: " + ValueToStringInternal(DirectiveScalar(42)));
    Message("directive.return.string: " + ValueToStringInternal(DirectiveScalar("x")));
    Message("directive.return.boolean: " + ValueToStringInternal(DirectiveScalar(True)));
    Message("directive.return.undefined: " + ValueToStringInternal(DirectiveScalar(Undefined)));
    Message("directive.call.recovery: " + ValueToStringInternal(DirectiveAdd()));
EndProcedure
