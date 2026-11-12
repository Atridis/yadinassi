// Explicit server form/object conversion observers, not standard form commands.
&AtServer
Procedure PrepareIndependentDraft()
 Raise "document independent flow not declared";
EndProcedure

&AtServerNoContext
Function UnitTag(Value)
 If TypeOf(Value) <> Type("EnumRef.Units") Then Return "other"; EndIf;
 If Value.IsEmpty() Then Return "empty"; EndIf;
 Return "unit" + Format(Enums.Units.IndexOf(Value), "NG=0");
EndFunction

&AtServerNoContext
Function StateTag(Value)
 If TypeOf(Value) <> Type("EnumRef.States") Then Return "other"; EndIf;
 If Value.IsEmpty() Then Return "empty"; EndIf;
 Return "state" + Format(Enums.States.IndexOf(Value), "NG=0");
EndFunction

&AtServer
Procedure PrepareRows(Flow)
 Object.Number = "EF00000" + Format(Flow, "NG=0"); Object.Date = Date(2024,1,1,12,0,0);
 Object.State = Enums.States.Approved;
 Object.Lines.Clear();
 One = Object.Lines.Add(); One.Unit = Enums.Units.Piece; One.Quantity = 1; One.Amount = 2;
 Two = Object.Lines.Add(); Two.Unit = Enums.Units.Pack; Two.Quantity = 3; Two.Amount = 4;
EndProcedure

&AtServerNoContext
Function MovementShape(Reference)
 Rows = AccumulationRegisters.Stock.CreateRecordSet();
 Rows.Filter.Recorder.Set(Reference); Rows.Read();
 Payload = Format(Rows.Count(), "NG=0");
 If Rows.Count() > 0 Then
  Payload = Payload + ";" + UnitTag(Rows[0].Unit) + ";" + StateTag(Rows[0].State);
 EndIf;
 Return Payload;
EndFunction

&AtServer
Function ObserveOwnedFlow(Flow, Instance)
 If Instance <> 1 Then Raise "document instance refused"; EndIf;
 If Flow = 4 Then
  Empty = StateTag(Object.State);
  Object.State = Enums.States.Draft; First = StateTag(Object.State);
  Object.State = Enums.States.Approved; Last = StateTag(Object.State);
  Payload = Empty + ";" + First + ";" + Last + ";" + ?(TypeOf(Object.State) = Type("EnumRef.States"), "1", "0");
 ElsIf Flow = 5 Then
  PrepareRows(Flow);
  First = UnitTag(Object.Lines[0].Unit); Second = UnitTag(Object.Lines[1].Unit);
  Object.Lines[0].Unit = Enums.Units.EmptyRef();
  Payload = First + ";" + Second + ";" + UnitTag(Object.Lines[0].Unit) + ";" + UnitTag(Object.Lines[1].Unit);
 ElsIf Flow = 6 Or Flow = 7 Then
  PrepareRows(Flow);
  Applied = FormAttributeToValue("Object"); Applied.Write(DocumentWriteMode.Posting);
  Reference = Applied.Ref;
  If Flow = 6 Then
   Fresh = Reference.GetObject(); ValueToFormAttribute(Fresh, "Object");
   Payload = ?(Fresh.Posted, "1", "0") + ";" + StateTag(Object.State) + ";" + UnitTag(Object.Lines[1].Unit) + ";" + MovementShape(Reference);
  Else
   Applied.Write(DocumentWriteMode.UndoPosting); Empty = MovementShape(Reference);
   Applied.Write(DocumentWriteMode.Posting); Restored = MovementShape(Reference);
   ValueToFormAttribute(Reference.GetObject(), "Object");
   Payload = Empty + ";" + Restored + ";" + ?(Object.Posted, "1", "0");
  EndIf;
 Else
  Raise "unsupported document observation";
 EndIf;
 Return New Structure("payload,reference", Payload, Undefined);
EndFunction
