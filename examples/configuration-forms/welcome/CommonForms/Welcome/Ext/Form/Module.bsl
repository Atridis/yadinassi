&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Hello from a configuration form";
EndProcedure
&AtClient
Procedure ShowDetails(Command)
 OpenForm("CommonForm.Details", New Structure("Message", Greeting));
EndProcedure
