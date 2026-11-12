// NEW acquisition fragment, not yet installed or called by a launcher.
// These methods are authored observers, NOT platform standard form commands.
&AtServer
Function ObserveCatalogFlow(Flow)
 If Flow = 1 Then
  Return EnumUnitTag(Object.Unit) + ";" + ?(TypeOf(Object.Unit) = Type("EnumRef.Units"), "1", "0");
 ElsIf Flow = 2 Then
  Object.Unit = Enums.Units.Piece;
  Named = EnumUnitTag(Object.Unit);
  // Deliberate direct observer call, not an automatic field OnChange event.
  ExplicitUnitObserver();
  Object.Unit = Enums.Units.EmptyRef();
  Cleared = EnumUnitTag(Object.Unit);
  ExplicitUnitObserver();
  Return Named + ";" + Cleared + ";" + Format(ExplicitChangeCount, "NG=0");
 ElsIf Flow = 3 Then
  Object.Code = "EF0001";
  Object.Description = "Owned enum form probe";
  Object.Unit = Enums.Units.Pack;
  Applied = FormAttributeToValue("Object");
  Applied.Write();
  Reference = Applied.Ref;
  Fresh = Reference.GetObject();
  ValueToFormAttribute(Fresh, "Object");
  Return EnumUnitTag(Object.Unit) + ";" + EnumUnitTag(Fresh.Unit) + ";" + ?(Reference.IsEmpty(), "1", "0");
 EndIf;
 Raise "unsupported owned catalog observation";
EndFunction

&AtServer
Procedure ExplicitUnitObserver()
 ExplicitChangeCount = ExplicitChangeCount + 1;
EndProcedure

&AtServerNoContext
Function EnumUnitTag(Value)
 If TypeOf(Value) <> Type("EnumRef.Units") Then Return "other"; EndIf;
 If Value.IsEmpty() Then Return "empty"; EndIf;
 Return "unit" + Format(Enums.Units.IndexOf(Value), "NG=0");
EndFunction

&AtServer
Procedure PrepareIndependentDraft()
 Object.Unit = ?(ProbeInstance = 1, Enums.Units.Piece, Enums.Units.Pack);
EndProcedure

&AtServer
Function ObserveOwnedFlow(Flow, Instance)
 If Flow = 8 Then
  Return New Structure("payload,reference", EnumUnitTag(Object.Unit), Undefined);
 EndIf;
 If Flow = 3 And Instance = 2 Then
  Applied = FormAttributeToValue("Object");
  Return New Structure("payload,reference", EnumUnitTag(Object.Unit) + ";" + ?(Applied.Ref.IsEmpty(), "1", "0"), Undefined);
 EndIf;
 Payload = ObserveCatalogFlow(Flow);
 Reference = Undefined;
 If Flow = 3 Then Reference = FormAttributeToValue("Object").Ref; EndIf;
 Return New Structure("payload,reference", Payload, Reference);
EndFunction
