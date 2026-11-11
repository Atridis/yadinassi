// Closed acquisition only. Five real owned form lifecycles, never direct event calls.
Var Request, Flow, Shared, CompletionCount, ResultKind, ResultMatches, WaitTurns, Records;

&AtClient
Procedure OwnerOpen(Cancel)
 Reader = New JSONReader; Reader.OpenFile(ПараметрЗапуска);
 Request = ReadJSON(Reader); Reader.Close();
 Flow = 0; Records = "";
 SaveJSON(Request.trace, New Structure("nonce,events", Request.nonce, New Array));
 Marker(Request.entered, "entered", "");
 AttachIdleHandler("NextFlow", 1, True);
EndProcedure

&AtClient
Procedure NextFlow() Export
 Flow = Flow + 1;
 If Flow > 5 Then
  Marker(Request.completed, "completed", Records);
  ЗавершитьРаботуСистемы(Ложь);
  Return;
 EndIf;
 Shared = New Structure("Seen", 0);
 CompletionCount = 0; ResultKind = "none"; ResultMatches = False; WaitTurns = 0;
 Trace("start");
 P = New Structure("Mode,TracePath,Nonce", Flow, Request.trace, Request.nonce);
 N = New CallbackDescription("Completed", ThisObject, Shared);
 OpenForm("ExternalDataProcessor.Launcher.Form.Child", P, ThisObject, Undefined, Undefined, Undefined, N);
 AttachIdleHandler("FinishFlow", 1, True);
EndProcedure

&AtClient
Procedure Completed(Result, Additional) Export
 CompletionCount = CompletionCount + 1;
 Additional.Seen = Additional.Seen + 1;
 If TypeOf(Result) = Type("String") Then
  ResultKind = "string"; ResultMatches = (Result = "chosen");
 ElsIf Result = Undefined Then
  ResultKind = "undefined"; ResultMatches = True;
 ElsIf TypeOf(Result) = Type("Structure") Then
  ResultKind = "structure"; ResultMatches = (Result.Code = "A" And Result.Count = 2);
 Else
  ResultKind = "other";
 EndIf;
 Trace("notify");
EndProcedure

&AtClient
Procedure FinishFlow() Export
 WaitTurns = WaitTurns + 1;
 If CompletionCount > 1 Or Shared.Seen > 1 Then
  Marker(Request.completed, "error", ""); ЗавершитьРаботуСистемы(Ложь); Return;
 EndIf;
 // Cancellation is a bounded observation, not an assumed no-callback rule.
 If (Flow < 5 And CompletionCount = 0) Or (Flow = 5 And WaitTurns < 3) Then
  If WaitTurns >= 10 Then
   Marker(Request.completed, "error", ""); ЗавершитьРаботуСистемы(Ложь); Return;
  EndIf;
  AttachIdleHandler("FinishFlow", 1, True); Return;
 EndIf;
 Trace("finish");
 T = LoadJSON(Request.trace); Codes = "";
 For Each E In T.events Do
  If E.flow = Flow Then Codes = Codes + E.code + ","; EndIf;
 EndDo;
 Records = Records + "FR" + String(Flow) + "=" + String(CompletionCount) + ";" + ResultKind + ";" + ?(ResultMatches,"1","0") + ";" + String(Shared.Seen) + ";" + Codes + "|";
 AttachIdleHandler("NextFlow", 1, True);
EndProcedure

&AtClient
Procedure Trace(Code)
 T = LoadJSON(Request.trace);
 If T.nonce <> Request.nonce Or T.events.Count() >= 64 Then Raise "trace refused"; EndIf;
 T.events.Add(New Structure("flow,code", Flow, Code)); SaveJSON(Request.trace, T);
EndProcedure

&AtClient
Function LoadJSON(Path)
 Reader = New JSONReader; Reader.OpenFile(Path); Value = ReadJSON(Reader); Reader.Close(); Return Value;
EndFunction

&AtClient
Procedure SaveJSON(Path, Value)
 Writer = New JSONWriter;
 Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(Path,,,Settings); WriteJSON(Writer, Value); Writer.Close();
EndProcedure

&AtClient
Procedure Marker(Path, Phase, Value)
 SaveJSON(Path, New Structure("schema,nonce,phase,source_sha256,form_sha256,records", "native-managed-form-results-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", Value));
EndProcedure
