&AtClient
Procedure IncrementClick(Command)
 IncrementAtServer();
EndProcedure
&AtServer
Procedure IncrementAtServer()
 Count = AddOne(Count);
EndProcedure
&AtServerNoContext
Function AddOne(Val Value)
 Return Value + 1;
EndFunction
