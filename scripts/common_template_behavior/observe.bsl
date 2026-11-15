// Raw observations of two owned resources. No expected-answer substitution.
Function ObserveCase(CaseNo, Stage)
    Stage="read";
    If CaseNo=1 Then Return String(TypeOf(GetCommonTemplate("OwnedText"))); EndIf;
    If CaseNo=2 Then Return GetCommonTemplate("OwnedText").GetText(); EndIf;
    If CaseNo=3 Then Return String(GetCommonTemplate("OwnedText").LineCount()); EndIf;
    If CaseNo=4 Then
        First=GetCommonTemplate("OwnedText"); First.SetText("changed");
        Return GetCommonTemplate("OwnedText").GetText();
    EndIf;
    If CaseNo=5 Then Return String(TypeOf(GetCommonTemplate("OwnedBinary"))); EndIf;
    If CaseNo=6 Then Return String(GetCommonTemplate("OwnedBinary").Size()); EndIf;
    If CaseNo=7 Then Return Base64String(GetCommonTemplate("OwnedBinary")); EndIf;
    If CaseNo=8 Then Return GetCommonTemplate("ownedtext").GetText(); EndIf;
    If CaseNo=9 Then
        Try Value=GetCommonTemplate("OwnedAbsent"); Return "returned:"+String(TypeOf(Value));
        Except Return "error"; EndTry;
    EndIf;
    If CaseNo=10 Then Return Metadata.CommonTemplates.OwnedText.Name; EndIf;
    If CaseNo=11 Then Return Metadata.CommonTemplates.OwnedText.FullName(); EndIf;
    If CaseNo=12 Then
        Try Value=GetCommonTemplate(Metadata.CommonTemplates.OwnedText); Return "returned:"+Value.GetText();
        Except Return "error"; EndTry;
    EndIf;
    Raise "unknown-owned-template-case";
EndFunction

For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); CommonTemplateEmit(CaseNo,Value);
    Except
        CommonTemplateDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
