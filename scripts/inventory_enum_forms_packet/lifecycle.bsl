// Actual configuration-owned lifecycle bindings. Never invoked by the launcher.
&AtServer
Procedure ObservedCreate(Cancel, StandardProcessing)
 A = New Array;
 A.Add(New FormAttribute("ProbeFlow", New TypeDescription("Number")));
 A.Add(New FormAttribute("ProbeInstance", New TypeDescription("Number")));
 A.Add(New FormAttribute("ProbeWaits", New TypeDescription("Number")));
 A.Add(New FormAttribute("ExplicitChangeCount", New TypeDescription("Number")));
 A.Add(New FormAttribute("ProbeTracePath", New TypeDescription("String")));
 A.Add(New FormAttribute("ProbeNonce", New TypeDescription("String")));
 ChangeAttributes(A);
 ThisObject.ProbeFlow = Parameters.Flow; ThisObject.ProbeInstance = Parameters.Instance;
 ThisObject.ProbeTracePath = Parameters.TracePath; ThisObject.ProbeNonce = Parameters.Nonce;
 ThisObject.ProbeWaits = 0; ThisObject.ExplicitChangeCount = 0;
 AppendLifecycle(ThisObject.ProbeTracePath, ThisObject.ProbeNonce, ThisObject.ProbeFlow, ThisObject.ProbeInstance, "create");
 If ThisObject.ProbeFlow = 8 Then PrepareIndependentDraft(); EndIf;
EndProcedure

&AtClient
Procedure ObservedOpen(Cancel)
 AppendLifecycle(ThisObject.ProbeTracePath, ThisObject.ProbeNonce, ThisObject.ProbeFlow, ThisObject.ProbeInstance, "open");
 AttachIdleHandler("ObserveAndClose", 1, True);
EndProcedure

&AtClient
Procedure ObserveAndClose() Export
 ThisObject.ProbeWaits = ThisObject.ProbeWaits + 1;
 If ThisObject.ProbeFlow = 8 And Not BothIndependentFormsOpened() Then
  If ThisObject.ProbeWaits >= 10 Then Raise "owned peer lifecycle incomplete"; EndIf;
  AttachIdleHandler("ObserveAndClose", 1, True); Return;
 EndIf;
 Result = ObserveOwnedFlow(ThisObject.ProbeFlow, ThisObject.ProbeInstance);
 AppendLifecycle(ThisObject.ProbeTracePath, ThisObject.ProbeNonce, ThisObject.ProbeFlow, ThisObject.ProbeInstance, "observed");
 // These are authored observers, not a standard Write/Post form command.
 Modified = False;
 Close(Result);
EndProcedure

&AtClient
Function BothIndependentFormsOpened()
 Reader = New JSONReader; Reader.OpenFile(ThisObject.ProbeTracePath);
 T = ReadJSON(Reader); Reader.Close();
 If T.nonce <> ThisObject.ProbeNonce Then Raise "owned trace binding refused"; EndIf;
 One = False; Two = False;
 For Each E In T.events Do
  If E.flow = 8 And E.code = "open" Then
   If E.instance = 1 Then One = True; EndIf;
   If E.instance = 2 Then Two = True; EndIf;
  EndIf;
 EndDo;
 Return One And Two;
EndFunction

&AtClientAtServerNoContext
Procedure AppendLifecycle(ProbeTracePath, ProbeNonce, ProbeFlow, ProbeInstance, EventCode)
 Reader = New JSONReader; Reader.OpenFile(ProbeTracePath);
 T = ReadJSON(Reader); Reader.Close();
 If T.nonce <> ProbeNonce Or T.events.Count() >= 64 Then Raise "owned lifecycle trace refused"; EndIf;
 If (ProbeFlow < 1 Or ProbeFlow > 8) Or (ProbeInstance <> 1 And ProbeInstance <> 2) Then Raise "owned lifecycle identity refused"; EndIf;
 If EventCode <> "create" And EventCode <> "open" And EventCode <> "observed" Then Raise "owned lifecycle event refused"; EndIf;
 T.events.Add(New Structure("flow,instance,code", ProbeFlow, ProbeInstance, EventCode));
 Writer = New JSONWriter; Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет, " ", True);
 Writer.OpenFile(ProbeTracePath,,,Settings); WriteJSON(Writer, T); Writer.Close();
EndProcedure
