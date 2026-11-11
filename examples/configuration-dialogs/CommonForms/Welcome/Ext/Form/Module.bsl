Var Shared;
&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Editable owner draft";
 LastAnswer = "No answer yet";
EndProcedure
&AtClient
Procedure AskQuestion(Command)
 Shared = New Structure("Calls", 0);
 Completion = New CallbackDescription("QuestionCompleted", ThisObject, Shared);
 ShowQueryBox(Completion, "Apply the approved value to this draft?", QuestionDialogMode.YesNoCancel,
  Undefined, Undefined, "Confirm draft change");
EndProcedure
&AtClient
Procedure ShowWarning(Command)
 Shared = New Structure("Calls", 0);
 Completion = New CallbackDescription("WarningCompleted", ThisObject, Shared);
 ShowMessageBox(Completion, "This warning does not change the owner draft.", Undefined, "Review notice");
EndProcedure
&AtClient
Procedure QuestionCompleted(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 CompletionCount = CompletionCount + 1;
 If Result = DialogReturnCode.Yes Then
  Greeting = "Approved value";
  LastAnswer = "Yes";
 ElsIf Result = DialogReturnCode.No Then
  LastAnswer = "No";
 Else
  LastAnswer = "Cancel";
 EndIf;
 Message("Completion count: " + String(AdditionalParameters.Calls));
 Message("Additional parameters shared: " + String(AdditionalParameters = Shared));
EndProcedure
&AtClient
Procedure WarningCompleted(AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 CompletionCount = CompletionCount + 1;
 LastAnswer = "Warning dismissed";
 Message("Completion count: " + String(AdditionalParameters.Calls));
 Message("Additional parameters shared: " + String(AdditionalParameters = Shared));
EndProcedure
&AtClient
Procedure ShowDetails(Command)
 Shared = New Structure("Calls", 0);
 Completion = New CallbackDescription("FormCompleted", ThisObject, Shared);
 OpenForm("CommonForm.Details", New Structure("Message", Greeting), ThisObject,
  Undefined, Undefined, Undefined, Completion);
EndProcedure
&AtClient
Procedure FormCompleted(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 If Result <> Undefined Then Greeting = Result.Text; EndIf;
 LastAnswer = "Owned form closed";
EndProcedure
