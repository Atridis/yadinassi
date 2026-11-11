// Fixed private trace is owned by the acquisition; never an application path.
&AtServer
Procedure ChildCreate(Cancel, StandardProcessing)
 A = New Array;
 A.Add(New FormAttribute("Mode", New TypeDescription("Number")));
 A.Add(New FormAttribute("TracePath", New TypeDescription("String")));
 A.Add(New FormAttribute("InvocationNonce", New TypeDescription("String")));
 A.Add(New FormAttribute("Attempts", New TypeDescription("Number")));
 ChangeAttributes(A);
 ThisObject.Mode = Parameters.Mode;
 ThisObject.TracePath = Parameters.TracePath;
 ThisObject.InvocationNonce = Parameters.Nonce;
 ThisObject.Attempts = 0;
EndProcedure

&AtClient
Procedure ChildOpen(Cancel)
 Trace("open");
 If Mode = 5 Then
  Trace("cancel_open"); Cancel = True; Return;
 EndIf;
 AttachIdleHandler("TryClose", 1, True);
EndProcedure

&AtClient
Procedure TryClose() Export
 Trace("request_close");
 If Mode = 2 Then
  Close();
 ElsIf Mode = 3 Then
  Close(New Structure("Code,Count", "A", 2));
 Else
  Close("chosen");
 EndIf;
EndProcedure

&AtClient
Procedure ChildBeforeClose(Cancel, Exit, MessageText, StandardProcessing)
 Attempts = Attempts + 1;
 Trace("before_close");
 If Mode = 4 And Attempts = 1 Then
  Cancel = True; Trace("refuse_close");
  AttachIdleHandler("TryClose", 1, True);
 EndIf;
EndProcedure

&AtClient
Procedure ChildClosed(Exit)
 Trace("closed");
EndProcedure

&AtClient
Procedure Trace(Code)
 Reader = New JSONReader; Reader.OpenFile(TracePath); T = ReadJSON(Reader); Reader.Close();
 If T.nonce <> InvocationNonce Or T.events.Count() >= 64 Then Raise "trace refused"; EndIf;
 T.events.Add(New Structure("flow,code", Mode, Code));
 Writer = New JSONWriter;
 Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(TracePath,,,Settings); WriteJSON(Writer,T); Writer.Close();
EndProcedure
