// Owned client-only observations. No ServerCall or dual-cache parity claim.
&AtClient
Var Request, Records, Calls, SessionToken, RequestToken, Finished;

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
  Return Bit(ReuseSession.Token("same") = ReuseSession.Token("same"));
 ElsIf Number = 2 Then
  Return Bit(ReuseSession.Token("a") = ReuseSession.Token("b"));
 ElsIf Number = 3 Then
  Return Bit(ReuseSession.Token() = ReuseSession.Token("default"));
 ElsIf Number = 4 Then
  A = ReuseSession.Token(Undefined); B = ReuseSession.Token(Null);
  C = ReuseSession.Token(True); D = ReuseSession.Token(1);
  Return Bit(A = B) + ":" + Bit(C = D);
 ElsIf Number = 5 Then
  A = New Structure("A,B", 1, "x"); B = New Structure("B,A", "x", 1);
  Return Bit(ReuseSession.Token(A) = ReuseSession.Token(B));
 ElsIf Number = 6 Then
  A = 0; First = ReuseSession.ChangeScalar(A);
  B = 0; Second = ReuseSession.ChangeScalar(B);
  Return Bit(First = Second) + ":" + String(A) + ":" + String(B);
 ElsIf Number = 7 Then
  A = New Structure("Seen", 0); B = New Structure("Seen", 0);
  First = ReuseSession.ChangeStructure(A); Second = ReuseSession.ChangeStructure(B);
  Return Bit(First = Second) + ":" + String(A.Seen) + ":" + String(B.Seen);
 ElsIf Number = 8 Then
  A = ReuseSession.Mutable("mutable"); A.Add("changed"); B = ReuseSession.Mutable("mutable");
  Return Bit(A[0] = B[0]) + ":" + String(B.Count());
 ElsIf Number = 9 Then
  Return Bit(ReuseSession.EmptyResult("empty") = Undefined) + ":" + Bit(ReuseSession.EmptyResult("empty") = Undefined);
 ElsIf Number = 10 Then
  A = "none"; B = "none";
  Try ReuseSession.Failing("failure"); Except A = ErrorDescription(); EndTry;
  Try ReuseSession.Failing("failure"); Except B = ErrorDescription(); EndTry;
  Return Bit(A = B) + ":" + Bit(A = "none") + ":" + Bit(B = "none");
 ElsIf Number = 11 Then
  State = New Structure("Seen", 0); ReuseSession.Touch(State); ReuseSession.Touch(State);
  Return String(State.Seen);
 ElsIf Number = 12 Then
  Return Bit(ReuseSession.InternalPair("inner")) + ":" + Bit(ReuseSession.QualifiedPair("qualified"));
 ElsIf Number = 13 Then
  Calls = 0; A = ReuseSession.Token(ArgumentValue()); B = ReuseSession.Token(ArgumentValue());
  Return Bit(A = B) + ":" + String(Calls);
 ElsIf Number = 14 Then
  A = ReuseSession.Token("refresh"); B = ReuseRequest.Token("refresh");
  RefreshReusableValues();
  Return Bit(A = ReuseSession.Token("refresh")) + ":" + Bit(B = ReuseRequest.Token("refresh"));
 ElsIf Number = 15 Then
  SessionToken = ReuseSession.Token("lifetime"); RequestToken = ReuseRequest.Token("lifetime");
  Return Bit(SessionToken = ReuseSession.Token("lifetime")) + ":" + Bit(RequestToken = ReuseRequest.Token("lifetime"));
 EndIf;
 Return "error";
EndFunction

&AtClient
Procedure FirstEvent() Export
 Try
  For Number = 1 To 15 Do
   Try Value = Observe(Number); Except Value = "error"; EndTry;
   Records = Records + "CM" + String(Number) + "=" + Value + "|";
  EndDo;
  Marker(Request.event1_done, "event1_done", Records);
  // Returning to the event loop is essential. Never call SecondEvent directly.
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
  Value = Bit(SessionToken = ReuseSession.Token("lifetime")) + ":" + Bit(RequestToken = ReuseRequest.Token("lifetime"));
  Records = Records + "CM16=" + Value + "|";
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
 WriteJSON(Writer, New Structure("schema,nonce,phase,source_sha256,form_sha256,modules_sha256,records", "native-common-module-reuse-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", "MODULES_VALUE", Value));
 Writer.Close();
EndProcedure
