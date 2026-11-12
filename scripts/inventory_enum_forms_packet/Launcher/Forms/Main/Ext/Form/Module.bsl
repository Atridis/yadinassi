// Bounded orchestration only. Never calls the child's lifecycle or observer.
&AtClient
Var Request, Flow, WaitTurns, CompletedCount, ExpectedCount, SeenOne, SeenTwo, PayloadOne, PayloadTwo, ReopenKey, Records;

&AtClient
Procedure OwnerOpen(Cancel)
 Try
  Request = LoadJSON(ПараметрЗапуска);
  Marker(Request.entered, "entered", "");
  SaveJSON(Request.trace, New Structure("nonce,events", Request.nonce, New Array));
  Flow = 0; Records = "";
  AttachIdleHandler("NextFlow", 1, True);
 Except
  ЗавершитьРаботуСистемы(Ложь);
 EndTry;
EndProcedure

&AtClient
Procedure NextFlow() Export
 Flow = Flow + 1;
 If Flow > 8 Then
  Marker(Request.completed, "completed", Records);
  ЗавершитьРаботуСистемы(Ложь); Return;
 EndIf;
 WaitTurns = 0; CompletedCount = 0; ExpectedCount = ?(Flow = 3 Or Flow = 8, 2, 1);
 SeenOne = False; SeenTwo = False; PayloadOne = ""; PayloadTwo = ""; ReopenKey = Undefined;
 OpenOwned(1, Undefined);
 If Flow = 8 Then OpenOwned(2, Undefined); EndIf;
 AttachIdleHandler("FinishFlow", 1, True);
EndProcedure

&AtClient
Procedure OpenOwned(Instance, Key)
 P = New Structure("Flow,Instance,TracePath,Nonce", Flow, Instance, Request.trace, Request.nonce);
 If Key <> Undefined Then P.Insert("Key", Key); EndIf;
 N = New CallbackDescription("Completed", ThisObject, New Structure("Flow,Instance", Flow, Instance));
 Name = ?(Flow <= 3 Or Flow = 8, "Catalog.Products.Form.Card", "Document.Receipt.Form.Card");
 // True forces a distinct instance. No reuse of an earlier managed form.
 OpenForm(Name, P, ThisObject, True, Undefined, Undefined, N);
EndProcedure

&AtClient
Procedure Completed(Result, Additional) Export
 If Additional.Flow <> Flow Or TypeOf(Result) <> Type("Structure") Then Raise "owned callback identity refused"; EndIf;
 If TypeOf(Result.payload) <> Type("String") Or StrLen(Result.payload) > 512 Then Raise "owned observation size refused"; EndIf;
 If Additional.Instance = 1 And Not SeenOne Then
  SeenOne = True; PayloadOne = Result.payload; ReopenKey = Result.reference;
 ElsIf Additional.Instance = 2 And Not SeenTwo Then
  SeenTwo = True; PayloadTwo = Result.payload;
 Else
  Raise "owned callback repeated";
 EndIf;
 CompletedCount = CompletedCount + 1;
EndProcedure

&AtClient
Procedure FinishFlow() Export
 WaitTurns = WaitTurns + 1;
 If Flow = 3 And CompletedCount = 1 And ReopenKey <> Undefined Then
  Key = ReopenKey; ReopenKey = Undefined;
  OpenOwned(2, Key);
 EndIf;
 If CompletedCount <> ExpectedCount Then
  If WaitTurns >= 15 Then ЗавершитьРаботуСистемы(Ложь); Return; EndIf;
  AttachIdleHandler("FinishFlow", 1, True); Return;
 EndIf;
 Names = StrSplit("catalog_default,catalog_change,catalog_reopen,document_header,document_rows,conversion_post,conversion_unpost,independent_forms", ",");
 Value = PayloadOne;
 If ExpectedCount = 2 Then Value = Value + ";" + PayloadTwo; EndIf;
 Records = Records + Names[Flow - 1] + "=" + Value + Chars.LF;
 AttachIdleHandler("NextFlow", 1, True);
EndProcedure

&AtClient
Function LoadJSON(Path)
 Reader = New JSONReader; Reader.OpenFile(Path); Value = ReadJSON(Reader); Reader.Close(); Return Value;
EndFunction

&AtClient
Procedure SaveJSON(Path, Value)
 Writer = New JSONWriter; Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(Path,,,Settings); WriteJSON(Writer, Value); Writer.Close();
EndProcedure

&AtClient
Procedure Marker(Path, Phase, Value)
 SaveJSON(Path, New Structure("schema,nonce,phase,source_sha256,form_sha256,records", "native-owned-enum-forms-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", Value));
EndProcedure
