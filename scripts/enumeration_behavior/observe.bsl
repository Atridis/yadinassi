// Owned native observation body. The source-bound launcher supplies framing.
// Returned strings are observations, not a table of expected answers.
Function ObserveCase(CaseNo, Stage)
    Stage = "read";
    Manager = Enums.OwnedStatus;
    If CaseNo = 1 Then Return String(Manager.Count()); EndIf;
    If CaseNo = 2 Then Return String(Manager.Get(0) = Manager.Active); EndIf;
    If CaseNo = 3 Then Return String(Manager.IndexOf(Manager.Closed)); EndIf;
    If CaseNo = 4 Then Return String(Manager.EmptyRef().IsEmpty()); EndIf;
    If CaseNo = 5 Then Return Metadata.Enums.OwnedStatus.FullName(); EndIf;
    If CaseNo = 6 Then Return String(Manager); EndIf;
    If CaseNo = 7 Then Return String(TypeOf(Manager.Active) = Type("EnumRef.OwnedStatus")); EndIf;
    If CaseNo = 8 Then Return String(TypeOf(Manager)); EndIf;
    If CaseNo = 9 Then Return String(Manager.Active); EndIf;
    If CaseNo = 10 Then Return String(Manager.EmptyRef()); EndIf;
    If CaseNo = 11 Then Return String(Metadata.Enums.OwnedStatus.EnumValues.Count()); EndIf;
    If CaseNo = 12 Then Return Metadata.Enums.OwnedStatus.EnumValues.Get(0).Name; EndIf;
    If CaseNo = 13 Then Return String(Metadata.FindByType(TypeOf(Manager.Active)) = Metadata.Enums.OwnedStatus); EndIf;
    If CaseNo = 14 Then
        Types = New Array; Types.Add(TypeOf(Manager.Active)); D = New TypeDescription(Types);
        Return String(D.ContainsType(TypeOf(Manager.Closed)));
    EndIf;
    If CaseNo = 15 Then Return String(ValueIsFilled(Manager.EmptyRef())); EndIf;
    If CaseNo = 16 Then
        Count = 0; For Each Value In Manager Do Count = Count + 1; EndDo;
        Return String(Count);
    EndIf;
    Raise "unknown-owned-enumeration-case";
EndFunction

For CaseNo = 1 To 16 Do
    Stage = "setup";
    Try
        Value = ObserveCase(CaseNo,Stage); EnumerationEmit(CaseNo,Value);
    Except
        EnumerationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
