// Измерение профиля компиляции; наружу выходят только ограниченные числовые коды.
&AtClient
Var Request, Records, Finished;

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
Function Observe(Number)
 If Number = 1 Then Return CPMaskEN()+":"+CPMaskRU();
 ElsIf Number = 2 Then Return ServerProbe.CPState();
 ElsIf Number = 3 Then Return ClientProbe.CPMaskEN()+":"+ClientProbe.CPMaskRU();
 ElsIf Number = 4 Then Return ServerProbe.CPMaskEN()+":"+ServerProbe.CPMaskRU();
 ElsIf Number = 5 Then Return DualProbe.CPMaskEN()+":"+DualProbe.CPMaskRU();
 ElsIf Number = 6 Then Return ServerProbe.DualMask();
 ElsIf Number = 7 Then
  A="0"; Try Execute("A=DualProbe.ClientExport();"); Except A="99"; EndTry; Return A;
 ElsIf Number = 8 Then
  A="0"; Try Execute("A=DualProbe.ServerExport();"); Except A="99"; EndTry; Return A;
 ElsIf Number = 9 Then Return ServerProbe.DualExports();
 ElsIf Number = 10 Then Return DualProbe.CPMobileEN()+":"+DualProbe.CPMobileRU()+":"+ServerProbe.DualMobile();
 ElsIf Number = 11 Then Return CPMobileEN();
 ElsIf Number = 12 Then Return CPMobileRU();
 ElsIf Number = 13 Then Return ClientProbe.CPMobileEN()+":"+ClientProbe.CPMobileRU();
 ElsIf Number = 14 Then Return ServerProbe.CPMobileEN()+":"+ServerProbe.CPMobileRU();
 ElsIf Number = 15 Then Return CPStartupValue();
 ElsIf Number = 16 Then
  A="0"; Try Execute("A=DualProbe.ExcludedExport();"); Except A="99"; EndTry; Return A;
 EndIf;
 Return "99";
EndFunction

&AtClient
Procedure FirstEvent() Export
 Try
  For Number = 1 To 15 Do
   Value = Observe(Number);
   Records = Records + "CP" + String(Number) + "=" + Value + "|";
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
  Value = Observe(16);
  Records = Records + "CP16=" + Value + "|";
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
 WriteJSON(Writer, New Structure("schema,nonce,phase,source_sha256,form_sha256,modules_sha256,records", "native-compilation-profile-v1", Request.nonce, Phase, "SOURCE_VALUE", "FORM_VALUE", "MODULES_VALUE", Value));
 Writer.Close();
EndProcedure
