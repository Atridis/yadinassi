// Future-scope measurement only: annotated module variables not yet supported.
&AtServer
Var ServerCounter;

&AtServer
Function NestedCounter()
    ServerCounter = ServerCounter + 1;
    Return ServerCounter;
EndFunction

&AtServer
Function OuterCounter()
    Before = ValueToStringInternal(ServerCounter);
    ServerCounter = 1;
    Inside = NestedCounter();
    Return Before + ";" + ValueToStringInternal(Inside)
        + ";" + ValueToStringInternal(ServerCounter);
EndFunction

&AtClient
Procedure Probe() Export
    Message("directive.state.first: " + OuterCounter());
    Message("directive.state.second: " + OuterCounter());
EndProcedure
