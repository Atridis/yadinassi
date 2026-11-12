// Candidate owned native observations. No acquisition or parity claim yet.
// Integrate only in a separately bound managed-form runner after review.
&AtClient
Var Flow, Shared, Calls, Returned, Finished;

&AtClient
Procedure BeginDialogs() Export
 Flow = 0; Finished = False;
 AttachIdleHandler("NextDialog", 1, True);
EndProcedure

&AtClient
Procedure NextDialog() Export
 Flow = Flow + 1;
 If Flow > 6 Then
  Finished = True;
  Return;
 EndIf;
 Shared = New Structure("Seen", 0);
 Calls = 0; Returned = "pending";
 If Flow = 5 Then
  ShowMessageBox(New CallbackDescription("WarningDone", ThisObject, Shared), "Owned warning", 1, "Owned probe");
 ElsIf Flow = 6 Then
  // Omitted timeout-button observation: do not assume its return code.
  ShowQueryBox(New CallbackDescription("QuestionDone", ThisObject, Shared), "Owned question", QuestionDialogMode.YesNo, 1);
 Else
  If Flow = 1 Then
   Mode = QuestionDialogMode.OK; Default = DialogReturnCode.OK; Timed = DialogReturnCode.OK;
  ElsIf Flow = 2 Then
   Mode = QuestionDialogMode.OKCancel; Default = DialogReturnCode.OK; Timed = DialogReturnCode.Cancel;
  ElsIf Flow = 3 Then
   Mode = QuestionDialogMode.YesNo; Default = DialogReturnCode.Yes; Timed = DialogReturnCode.No;
  Else
   Mode = QuestionDialogMode.YesNoCancel; Default = DialogReturnCode.Yes; Timed = DialogReturnCode.Cancel;
  EndIf;
  ShowQueryBox(New CallbackDescription("QuestionDone", ThisObject, Shared), "Owned question", Mode, 1, Default, "Owned probe", Timed);
 EndIf;
 // No next dialog here: native completion must arrive before continuation.
EndProcedure

&AtClient
Procedure QuestionDone(Result, AdditionalParameters) Export
 Calls = Calls + 1;
 AdditionalParameters.Seen = AdditionalParameters.Seen + 1;
 If Result = DialogReturnCode.OK Then Returned = "ok";
 ElsIf Result = DialogReturnCode.Cancel Then Returned = "cancel";
 ElsIf Result = DialogReturnCode.Yes Then Returned = "yes";
 ElsIf Result = DialogReturnCode.No Then Returned = "no";
 ElsIf Result = DialogReturnCode.Timeout Then Returned = "timeout";
 Else Returned = "other";
 EndIf;
 // The owned runner will append bounded ordinal/count/code/identity evidence,
 // then schedule NextDialog outside this callback. No direct callback calls.
EndProcedure

&AtClient
Procedure WarningDone(AdditionalParameters) Export
 Calls = Calls + 1;
 AdditionalParameters.Seen = AdditionalParameters.Seen + 1;
 Returned = "warning";
EndProcedure
