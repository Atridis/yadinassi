// Owned scalar-only dual-cache observations. Tokens never leave as raw records.
&AtClient
Var Request, Records, Calls, ClientToken, SessionToken, RequestToken, Finished;

&AtClient
Procedure OwnerOpen(Cancel)
 Try
  Reader = New JSONReader; Reader.OpenFile(ПараметрЗапуска);
  Request = ReadJSON(Reader); Reader.Close();
  Records = ""; Finished = False;
  Marker(Request.entered, "entered", "");
  AttachIdleHandler("FirstEvent", 1, True);
 Except
  ЗавершитьРаботуСистемы(Ложь);
 EndTry;
EndProcedure

&AtClient
Function Bit(Value)
 If Value Then Return "1"; Else Return "0"; EndIf;
EndFunction

&AtClient
Function ArgumentValue()
 Calls = Calls + 1;
 Return "argument";
EndFunction

&AtClient
Function Observe(Number)
 If Number = 1 Then
  Return Bit(CachedServerCall.Token("same") = CachedServerCall.Token("same"));
 ElsIf Number = 2 Then
  Return Bit(CachedServerCall.Token("a") = CachedServerCall.Token("b"));
 ElsIf Number = 3 Then
  A = CachedServerCall.Token("layers");
  Return Bit(A = ServerInspector.DirectToken("layers"));
 ElsIf Number = 4 Then
  A = CachedServerCall.Token("client-refresh");
  RefreshReusableValues();
  Return Bit(A = CachedServerCall.Token("client-refresh"));
 ElsIf Number = 5 Then
  A = CachedServerCall.Token("server-refresh");
  ServerInspector.RefreshServer();
  B = ServerInspector.DirectToken("server-refresh");
  Return Bit(A = CachedServerCall.Token("server-refresh")) + ":" + Bit(A = B);
 ElsIf Number = 6 Then
  A = CachedServerCall.Token("both-refresh");
  ServerInspector.RefreshServer(); RefreshReusableValues();
  Return Bit(A = CachedServerCall.Token("both-refresh"));
 ElsIf Number = 7 Then
  Return Bit(ServerInspector.SessionPair("qualified"));
 ElsIf Number = 8 Then
  Return Bit(ServerInspector.InternalPair("unqualified"));
 ElsIf Number = 9 Then
  Return Bit(ServerInspector.RequestPair("request-pair"));
 ElsIf Number = 10 Then
  A = ServerInspector.RequestToken("request-separate");
  Return Bit(A = ServerInspector.RequestToken("request-separate"));
 ElsIf Number = 11 Then
  A = ServerInspector.SessionToken("session-separate");
  Return Bit(A = ServerInspector.SessionToken("session-separate"));
 ElsIf Number = 12 Then
  A = "none"; B = "none";
  For Attempt = 1 To 2 Do
   Try CachedServerCall.Failing("failure"); Except Failure = ErrorDescription(); EndTry;
   If Attempt = 1 Then A = Failure; Else B = Failure; EndIf;
  EndDo;
  Return Bit(A = B) + ":" + Bit(A = "none") + ":" + Bit(B = "none");
 ElsIf Number = 13 Then
  Calls = 0;
  A = CachedServerCall.Token(ArgumentValue()); B = CachedServerCall.Token(ArgumentValue());
  Return Bit(A = B) + ":" + String(Calls);
 ElsIf Number = 14 Then
  ClientToken = CachedServerCall.Token("lifetime");
  SessionToken = ServerInspector.SessionToken("lifetime");
  RequestToken = ServerInspector.RequestToken("lifetime");
  Return Bit(ClientToken = CachedServerCall.Token("lifetime")) + ":" + Bit(SessionToken = ServerInspector.SessionToken("lifetime"));
 ElsIf Number = 15 Then
  Return Bit(ServerInspector.RequestPair("request-last"));
 EndIf;
 Return "error";
EndFunction

&AtClient
Procedure FirstEvent() Export
 Try
  For Number = 1 To 15 Do
   Try Value = Observe(Number); Except Value = "error"; EndTry;
   Records = Records + "SR" + String(Number) + "=" + Value + "|";
  EndDo;
  Marker(Request.event1_done, "event1_done", Records);
  // Actual event-loop return, never call SecondEvent directly.
  AttachIdleHandler("SecondEvent", 1, True);
 Except
  Marker(Request.completed, "error", ""); ЗавершитьРаботуСистемы(Ложь);
 EndTry;
EndProcedure

&AtClient
Procedure SecondEvent() Export
 If Finished Then Return; EndIf;
 Finished = True;
 Try
  Value = Bit(ClientToken = CachedServerCall.Token("lifetime")) + ":" + Bit(SessionToken = ServerInspector.SessionToken("lifetime")) + ":" + Bit(RequestToken = ServerInspector.RequestToken("lifetime"));
  Records = Records + "SR16=" + Value + "|";
  Marker(Request.completed, "completed", Records);
 Except
  Marker(Request.completed, "error", "");
 EndTry;
 ЗавершитьРаботуСистемы(Ложь);
EndProcedure

&AtClient
Procedure Marker(Path, Phase, Value)
 Writer = New JSONWriter;
 Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(Path,,,Settings);
 WriteJSON(Writer, New Structure("schema,nonce,phase,source_sha256,form_sha256,modules_sha256,records", "native-server-module-reuse-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", "MODULES_VALUE", Value));
 Writer.Close();
EndProcedure
