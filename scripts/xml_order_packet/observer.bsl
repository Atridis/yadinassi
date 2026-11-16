// Authored observers; native lifecycle dispatch must invoke these event handlers.
&AtClient
Procedure XmlOrderOpen(Cancel)
 If DraftTitle <> "XML-order witness" Or Amount <> 17 Or Comment <> "scope-check" Then
  Raise "xml order initial effect mismatch";
 EndIf;
 XmlOrderAppend("open_effect");
 Names = "";
 For Each Item In Items Do
  If Item.Name = "DraftTitleField" Or Item.Name = "AmountField" Or Item.Name = "CommentField"
   Or Item.Name = "KeepOpenField" Or Item.Name = "AcceptButton" Or Item.Name = "CancelButton" Then
   Names = Names + ?(Names = "", "", ",") + Item.Name;
  EndIf;
 EndDo;
 XmlOrderAppend("items:" + Names);
 AttachIdleHandler("XmlOrderStep", 1, True);
EndProcedure

&AtClient
Procedure XmlOrderStep() Export
 If ThisObject.XmlOrderStage = 0 Then
  ThisObject.XmlOrderStage = 1;
  KeepOpen = True;
  AttachIdleHandler("XmlOrderStep", 1, True);
  Close();
 Else
  // Reaching this idle callback after Close witnesses that cancellation kept the form alive.
  XmlOrderAppend("cancel_effect");
  KeepOpen = False;
  Modified = False;
  Close();
 EndIf;
EndProcedure

&AtClient
Procedure XmlOrderClosed()
 XmlOrderAppend("closed");
 ЗавершитьРаботуСистемы(Ложь);
EndProcedure

&AtClientAtServerNoContext
Procedure XmlOrderAppend(Code)
 Reader = New JSONReader; Reader.OpenFile("/tmp/xml-order/trace.json");
 T = ReadJSON(Reader); Reader.Close();
 If T.events.Count() >= 12 Then Raise "xml order event budget"; EndIf;
 T.events.Add(Code);
 Writer = New JSONWriter; Settings = New JSONWriterSettings(ПереносСтрокJSON.Нет, " ", True);
 Writer.OpenFile("/tmp/xml-order/trace.json",,,Settings); WriteJSON(Writer, T); Writer.Close();
EndProcedure
