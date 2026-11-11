&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Hello from the configuration application";
EndProcedure

&AtClient
Procedure ShowDetails(Command)
 Message(Service.Add(4));
 Tools.ShowDetails(Greeting);
EndProcedure
