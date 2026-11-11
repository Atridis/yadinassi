// Real owned input windows only; completion procedures are never called by the probe.
&AtClient
Var Flow, Shared, Calls, Returned, Identity, ValueMatch, Request, Records, Turns, Events, Items, ExpectedItem;

&AtClient
Procedure OwnerOpen(Cancel)
 Try
  Reader = New JSONReader; Reader.OpenFile(ПараметрЗапуска);
  Request = ReadJSON(Reader); Reader.Close();
  Marker(Request.entered, "entered", "");
  Flow = 0; Records = "";
  AttachIdleHandler("NextInput", 1, True);
 Except
  ЗавершитьРаботуСистемы(Ложь);
 EndTry;
EndProcedure

&AtClient
Procedure NextInput() Export
 Flow = Flow + 1;
 If Flow > 8 Then
  Marker(Request.completed, "completed", Records);
  ЗавершитьРаботуСистемы(Ложь); Return;
 EndIf;
 Shared = New Structure("Seen", 0); Calls = 0; Turns = 0;
 Returned = "pending"; Identity = 0; ValueMatch = 0; Events = "start,";
 Title = "YADINASSI-VI0" + String(Flow) + "-" + Request.nonce;
 Callback = New CallbackDescription("InputDone", ThisObject, Shared);
 If Flow = 6 Or Flow = 7 Then
  Items = New ValueList;
  Items.Add("first", "First");
  ExpectedItem = Items.Add("second", "Second");
  Items.ShowChooseItem(Callback, Title, ExpectedItem);
 ElsIf Flow = 2 Then
  ShowInputValue(Callback, 12.5, Title, Type("Number"));
 ElsIf Flow = 3 Then
  ShowInputValue(Callback, Date(2024, 2, 3, 4, 5, 6), Title, Type("Date"));
 ElsIf Flow = 4 Then
  ShowInputValue(Callback, True, Title, Type("Boolean"));
 Else
  ShowInputValue(Callback, "seed", Title, Type("String"));
 EndIf;
 Events = Events + "returned,";
 AttachIdleHandler("ObserveInput", 1, True);
EndProcedure

&AtClient
Procedure InputDone(Result, AdditionalParameters) Export
 Calls = Calls + 1; Events = Events + "callback,";
 AdditionalParameters.Seen = AdditionalParameters.Seen + 1;
 If Result = Undefined Then Returned = "undefined";
 ElsIf Flow = 6 Or Flow = 7 Then
  Returned = "item";
  If Result = ExpectedItem Then Identity = 1; EndIf;
  If Result.Value = "second" Then ValueMatch = 1; EndIf;
 ElsIf TypeOf(Result) = Type("String") Then
  Returned = "string";
  If (Flow = 1 And Result = "edited") Or (Flow = 8 And Result = "") Then ValueMatch = 1; EndIf;
 ElsIf TypeOf(Result) = Type("Number") Then
  Returned = "number"; If Result = 12.5 Then ValueMatch = 1; EndIf;
 ElsIf TypeOf(Result) = Type("Date") Then
  Returned = "date"; If Result = Date(2024, 2, 3, 4, 5, 6) Then ValueMatch = 1; EndIf;
 ElsIf TypeOf(Result) = Type("Boolean") Then
  Returned = "boolean"; If Result = True Then ValueMatch = 1; EndIf;
 Else Returned = "other";
 EndIf;
EndProcedure

&AtClient
Procedure ObserveInput() Export
 Turns = Turns + 1;
 If Calls = 0 And Turns < 12 Then AttachIdleHandler("ObserveInput", 1, True); Return; EndIf;
 If Calls <> 1 Or Shared.Seen < 0 Or Shared.Seen > 1 Then
  Marker(Request.completed, "error", ""); ЗавершитьРаботуСистемы(Ложь); Return;
 EndIf;
 Events = Events + "finish,";
 Records = Records + "VI" + String(Flow) + "=1;" + Returned + ";" + String(Shared.Seen) + ";" + String(Identity) + ";" + String(ValueMatch) + ";" + Events + "|";
 Items = Undefined; ExpectedItem = Undefined;
 AttachIdleHandler("NextInput", 1, True);
EndProcedure

&AtClient
Procedure Marker(Path, Phase, Value)
 Writer = New JSONWriter; Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(Path,,,Settings);
 WriteJSON(Writer, New Structure("schema,nonce,phase,source_sha256,form_sha256,records", "native-managed-value-inputs-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", Value));
 Writer.Close();
EndProcedure
