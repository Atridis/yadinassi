Var Extra;
&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Choose a value in the owned form";
EndProcedure
&AtClient
Procedure ShowDetails(Command)
 Extra = New Structure("Calls", 0);
 Completion = New CallbackDescription("Completed", ThisObject, Extra);
 OpenForm("CommonForm.Details", New Structure("Message", "A chosen value"), ThisObject,
  Undefined, Undefined, Undefined, Completion);
EndProcedure
&AtClient
Procedure Completed(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 If Result = Undefined Then
  Greeting = "Closed without a selection";
 Else
  Greeting = Result.Text;
 EndIf;
 Message("Completion count: " + String(AdditionalParameters.Calls));
EndProcedure
