// Owned native timeout observations. No keyboard/close/default-input parity claim.
&AtClient
Var Flow, Shared, Calls, Returned, Finished, Request, Records, Turns, Events;

&AtClient
Procedure OwnerOpen(Cancel)
 Try
  Reader = New JSONReader; Reader.OpenFile(ПараметрЗапуска);
  Request = ReadJSON(Reader); Reader.Close();
  Marker(Request.entered, "entered", "");
  Flow = 0; Finished = False; Records = "";
  AttachIdleHandler("NextDialog", 1, True);
 Except
  ЗавершитьРаботуСистемы(Ложь);
 EndTry;
EndProcedure

&AtClient
Procedure NextDialog() Export
 Flow = Flow + 1;
 If Flow > 6 Then
  Finished = True;
  Marker(Request.completed, "completed", Records);
  ЗавершитьРаботуСистемы(Ложь);
  Return;
 EndIf;
 Shared = New Structure("Seen", 0);
 Calls = 0; Returned = "pending"; Turns = 0; Events = "start,";
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
 Events = Events + "returned,";
 AttachIdleHandler("ObserveDialog", 1, True);
EndProcedure

&AtClient
Procedure QuestionDone(Result, AdditionalParameters) Export
 Calls = Calls + 1;
 Events = Events + "callback,";
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
 Events = Events + "callback,";
 AdditionalParameters.Seen = AdditionalParameters.Seen + 1;
 Returned = "warning";
EndProcedure

&AtClient
Procedure ObserveDialog() Export
 Turns = Turns + 1;
 If Calls = 0 And Turns < 15 Then
  AttachIdleHandler("ObserveDialog", 1, True); Return;
 EndIf;
 If Calls <> 1 Or Shared.Seen < 0 Or Shared.Seen > 1 Then
  Marker(Request.completed, "error", ""); ЗавершитьРаботуСистемы(Ложь); Return;
 EndIf;
 Events = Events + "finish,";
 Records = Records + "DG" + String(Flow) + "=" + String(Calls) + ";" + Returned + ";" + String(Shared.Seen) + ";" + Events + "|";
 AttachIdleHandler("NextDialog", 1, True);
EndProcedure

&AtClient
Procedure Marker(Path, Phase, Value)
 Writer = New JSONWriter;
 Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(Path,,,Settings);
 WriteJSON(Writer, New Structure("schema,nonce,phase,source_sha256,form_sha256,records", "native-managed-dialogs-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", Value));
 Writer.Close();
EndProcedure
