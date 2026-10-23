// Preparation only: no native expected values or runtime support are asserted.
// Side-local variables are not managed-form attributes and are never copied.
&AtClient
Var ContextClientCounter;
&AtServer
Var ContextServerCounter;
&AtServer
Var ContextServerUninitialized;

&AtServer
Function ContextModuleNested()
    ContextServerCounter = ContextServerCounter + 1;
    Return ContextServerCounter;
EndFunction

&AtServer
Function ContextModuleCall(Val Escape)
    Var Initial, Nested, WasUndefined;
    Initial = ContextServerCounter;
    WasUndefined = ContextServerUninitialized = Undefined;
    ContextServerCounter = ContextServerCounter + 10;
    ContextServerUninitialized = 7;
    Nested = ContextModuleNested();
    If Escape Then
        Raise "module-context-controlled-failure";
    EndIf;
    Return New Structure("Initial,Nested,WasUndefined", Initial, Nested, WasUndefined);
EndFunction

&AtClient
Procedure ContextModuleRecord(Val Label, Val Value)
    Message("module.context.core." + Label + ": " + ValueToStringInternal(Value));
EndProcedure

&AtClient
Procedure RunModuleContextProbe() Export
    Var First, Second, Third, Failed, Matched;
    ContextModuleRecord("client.initial", ContextClientCounter);
    ContextClientCounter = ContextClientCounter + 1;
    First = ContextModuleCall(False);
    ContextModuleRecord("server.initial", First.Initial);
    ContextModuleRecord("server.nested", First.Nested);
    ContextModuleRecord("server.undefined", First.WasUndefined);
    Second = ContextModuleCall(False);
    ContextModuleRecord("server.repeated.initial", Second.Initial);
    Failed = False;
    Matched = False;
    Try
        ContextModuleCall(True);
    Except
        Failed = True;
        Matched = Find(ErrorDescription(), "module-context-controlled-failure") > 0;
    EndTry;
    Third = ContextModuleCall(False);
    ContextModuleRecord("escaped.caught", Failed And Matched);
    ContextModuleRecord("server.recovery.initial", Third.Initial);
    ContextModuleRecord("server.recovery.undefined", Third.WasUndefined);
    ContextModuleRecord("client.retained", ContextClientCounter);
EndProcedure

// Initialization runs in its explicitly compiled side only. Do not infer that
// arbitrary unguarded standalone root statements should run on the server.
#If AtClient Then
ContextClientCounter = 10;
#EndIf
#If AtServer Then
ContextServerCounter = 100;
#EndIf
