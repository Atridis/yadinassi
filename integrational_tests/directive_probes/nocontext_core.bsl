// Measurement source only. No native expected values are asserted.
&AtServerNoContext
Function NoContextLeaf(Value)
    Value = Value + 1;
    Return Value;
EndFunction

&AtServerNoContext
Function NoContextOperation(Value, Val PrivateValue, Val Mode)
    Var Initial, Nested, ProfileMask, Caught;
    Initial = Value;
    Value = Value + 10;
    PrivateValue = PrivateValue + 20;
    Nested = NoContextLeaf(Value);
    ProfileMask = 0;
#If AtClient Then
    ProfileMask = ProfileMask + 1;
#EndIf
#If AtServer Then
    ProfileMask = ProfileMask + 2;
#EndIf
    Caught = False;
    If Mode = 1 Then
        Try
            Raise "nocontext-controlled-failure";
        Except
            Caught = Find(ErrorDescription(), "nocontext-controlled-failure") > 0;
        EndTry;
    EndIf;
    If Mode = 2 Then
        Raise "nocontext-controlled-failure";
    EndIf;
    Return New Structure("Initial,Nested,PrivateValue,ProfileMask,Caught", Initial, Nested, PrivateValue, ProfileMask, Caught);
EndFunction

&AtServer
Function NoContextFromContext(Val Escape)
    Var LocalValue, PrivateValue, Result, Failed, Matched;
    LocalValue = 3;
    PrivateValue = 4;
    Failed = False;
    Matched = False;
    Result = Undefined;
    Try
        If Escape Then
            Result = NoContextOperation(LocalValue, PrivateValue, 2);
        Else
            Result = NoContextOperation(LocalValue, PrivateValue, 0);
        EndIf;
    Except
        Failed = True;
        Matched = Find(ErrorDescription(), "nocontext-controlled-failure") > 0;
    EndTry;
    Return New Structure("Value,PrivateValue,Failed,Matched,Result", LocalValue, PrivateValue, Failed, Matched, Result);
EndFunction

&AtClient
Procedure NoContextRecord(Val Label, Val Value)
    Message("nocontext.core." + Label + ": " + ValueToStringInternal(Value));
EndProcedure

&AtClient
Procedure RunNoContextProbe() Export
    Var Value, PrivateValue, Result, Failed, Matched, Nested;
    Value = 1;
    PrivateValue = 2;
    Result = NoContextOperation(Value, PrivateValue, 0);
    NoContextRecord("normal.nested", Result.Nested);
    NoContextRecord("normal.private", Result.PrivateValue);
    NoContextRecord("normal.profile", Result.ProfileMask);
    NoContextRecord("normal.caller", Value);
    NoContextRecord("normal.val.caller", PrivateValue);
    Value = 5;
    Result = NoContextOperation(Value, PrivateValue, 1);
    NoContextRecord("caught.matched", Result.Caught);
    NoContextRecord("caught.caller", Value);
    Value = 6;
    Failed = False;
    Matched = False;
    Try
        NoContextOperation(Value, PrivateValue, 2);
    Except
        Failed = True;
        Matched = Find(ErrorDescription(), "nocontext-controlled-failure") > 0;
    EndTry;
    NoContextRecord("escape.caught", Failed And Matched);
    NoContextRecord("escape.caller", Value);
    Nested = NoContextFromContext(False);
    NoContextRecord("context.normal.value", Nested.Value);
    Nested = NoContextFromContext(True);
    NoContextRecord("context.escape.value", Nested.Value);
    NoContextRecord("context.escape.caught", Nested.Failed And Nested.Matched);
    Value = 7;
    Result = NoContextOperation(Value, PrivateValue, 0);
    NoContextRecord("recovery.initial", Result.Initial);
    NoContextRecord("recovery.caller", Value);
EndProcedure
