// Owned measurements: generated addresses never leave the bounded observations.
Function ObserveCase(CaseNo, Stage)
    Stage = "read";
    Owner = New UUID;
    If CaseNo = 1 Then
        Address = PutToTempStorage("value",Owner);
        Return String(TypeOf(Address)=Type("String"))+":"+String(IsTempStorageURL(Address))+":"+GetFromTempStorage(Address);
    EndIf;
    If CaseNo = 2 Then
        Address = PutToTempStorage(Undefined,Owner);
        Return String(GetFromTempStorage(Address)=Undefined);
    EndIf;
    If CaseNo = 3 Then
        Source = New Array; Source.Add("before"); Address = PutToTempStorage(Source,Owner); Source[0]="after";
        Return GetFromTempStorage(Address)[0];
    EndIf;
    If CaseNo = 4 Then
        Source = New Structure("Field","before"); Address = PutToTempStorage(Source,Owner); Copy = GetFromTempStorage(Address); Copy.Field="after";
        Return GetFromTempStorage(Address).Field;
    EndIf;
    If CaseNo = 5 Then
        Address = PutToTempStorage("first",Owner); Replaced = PutToTempStorage("second",Address);
        Return String(Address=Replaced)+":"+GetFromTempStorage(Address);
    EndIf;
    If CaseNo = 6 Then
        Address = PutToTempStorage("first",Owner); DeleteFromTempStorage(Address);
        Return String(IsTempStorageURL(Address))+":"+String(GetFromTempStorage(Address)=Undefined);
    EndIf;
    If CaseNo = 7 Then
        Address = PutToTempStorage("first",Owner); DeleteFromTempStorage(Address);
        Try DeleteFromTempStorage(Address); Return "deleted-again"; Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 8 Then Return String(IsTempStorageURL("not-a-storage-url")); EndIf;
    If CaseNo = 9 Then
        Try Value = GetFromTempStorage("not-a-storage-url"); Return "value:"+String(Value=Undefined); Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 10 Then
        Try DeleteFromTempStorage("not-a-storage-url"); Return "deleted"; Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 11 Then
        Address=PutToTempStorage("without-owner"); Return GetFromTempStorage(Address);
    EndIf;
    If CaseNo = 12 Then
        Try Address=PutToTempStorage("wrong-owner",42); Return "stored"; Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 13 Then
        Address=PutToTempStorage("first",Owner); DeleteFromTempStorage(Address);
        Try Replaced=PutToTempStorage("restored",Address); Return String(Address=Replaced)+":"+GetFromTempStorage(Address); Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 14 Then
        Source=New Map; Source.Insert("item",New Array); Source.Get("item").Add(12);
        Address=PutToTempStorage(Source,Owner); Return String(GetFromTempStorage(Address).Get("item")[0]);
    EndIf;
    If CaseNo = 15 Then
        Try Address=PutToTempStorage("empty-owner",""); Return "stored:"+GetFromTempStorage(Address); Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 16 Then
        Address=PutToTempStorage(False,Owner); Return String(GetFromTempStorage(Address));
    EndIf;
    Raise "unknown-owned-temporary-storage-case";
EndFunction

For CaseNo = 1 To 16 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); TemporaryStorageEmit(CaseNo,Value);
    Except
        TemporaryStorageDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
