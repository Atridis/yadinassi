Var Shared, Priorities, OriginalPriority;
&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Editable owner draft";
 LastAnswer = "No parameter entered";
EndProcedure
&AtClient
Procedure AskQuantity(Command)
 Shared = New Structure("Calls,Kind", 0, "Quantity");
 Completion = New CallbackDescription("InputCompleted", ThisObject, Shared);
 ShowInputValue(Completion, 12.5, "Quantity");
EndProcedure
&AtClient
Procedure AskDate(Command)
 Shared = New Structure("Calls,Kind", 0, "Date");
 Completion = New CallbackDescription("InputCompleted", ThisObject, Shared);
 ShowInputValue(Completion, Date(2024, 2, 3, 4, 5, 6), "Effective date and time");
EndProcedure
&AtClient
Procedure AskReason(Command)
 Shared = New Structure("Calls,Kind", 0, "Reason");
 Completion = New CallbackDescription("InputCompleted", ThisObject, Shared);
 ShowInputValue(Completion, "Draft" + Char(13) + Char(10) + "reason", "Reason");
EndProcedure
&AtClient
Procedure ChoosePriority(Command)
 Priorities = New ValueList;
 Priorities.Add("normal", "Normal processing");
 OriginalPriority = Priorities.Add("urgent", "Urgent processing");
 Shared = New Structure("Calls,Kind", 0, "Priority");
 Completion = New CallbackDescription("PriorityCompleted", ThisObject, Shared);
 Priorities.ShowChooseItem(Completion, "Choose priority", OriginalPriority);
EndProcedure
&AtClient
Procedure InputCompleted(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 CompletionCount = CompletionCount + 1;
 If Result = Undefined Then
  LastAnswer = AdditionalParameters.Kind + " cancelled";
 Else
  Greeting = String(Result);
  LastAnswer = AdditionalParameters.Kind + " confirmed";
 EndIf;
 Message("Additional parameters shared: " + String(AdditionalParameters = Shared));
EndProcedure
&AtClient
Procedure PriorityCompleted(Result, AdditionalParameters) Export
 AdditionalParameters.Calls = AdditionalParameters.Calls + 1;
 CompletionCount = CompletionCount + 1;
 If Result = Undefined Then
  LastAnswer = "Priority cancelled";
 Else
  Greeting = Result.Value;
  LastAnswer = "Priority confirmed";
  Message("Original second item: " + String(Result = OriginalPriority));
 EndIf;
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
