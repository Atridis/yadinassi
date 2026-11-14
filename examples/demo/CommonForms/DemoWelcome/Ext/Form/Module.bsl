&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Справочники, документы и отчёты работают в одной базе";
EndProcedure
&AtClient
Procedure ShowDetails(Command)
 Message(DemoService.Add(4));
 DemoTools.OpenOperation();
EndProcedure
