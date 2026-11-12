// Owned sequential observations, not an expected-answer table.
Function ObserveCase(CaseNo, Stage)
    Stage = "read";
    If CaseNo = 1 Then Return String(SessionParameters.OwnedStartup); EndIf;
    If CaseNo = 2 Then Return String(SessionParameters.OwnedStartupUndefined); EndIf;
    If CaseNo = 3 Then Return SessionParameters.OwnedLazy; EndIf;
    If CaseNo = 4 Then
        Value = SessionParameters.OwnedLazy;
        Return String(SessionParameters.OwnedCalls);
    EndIf;
    If CaseNo = 5 Then Return SessionParameters["OwnedLazy"]; EndIf;
    If CaseNo = 6 Then Return SessionParameters.OwnedLinked; EndIf;
    If CaseNo = 7 Then
        Try Value = SessionParameters.OwnedMissing; Return "value:" + String(Value);
        Except Return "error:" + String(SessionParameters.OwnedMissingCalls); EndTry;
    EndIf;
    If CaseNo = 8 Then
        SessionParameters.OwnedBoolean = False; Return String(SessionParameters.OwnedBoolean);
    EndIf;
    If CaseNo = 9 Then
        SessionParameters.OwnedDate = Date(2026,1,2,3,4,5);
        Return String(SessionParameters.OwnedDate = Date(2026,1,2,3,4,5));
    EndIf;
    If CaseNo = 10 Then
        Try SessionParameters.OwnedNumber = 12.345;
        Except Return "error"; EndTry;
        Return "assigned:" + String(SessionParameters.OwnedNumber);
    EndIf;
    If CaseNo = 11 Then
        Try SessionParameters.OwnedString = "abcdefg";
        Except Return "error"; EndTry;
        Return "assigned:" + SessionParameters.OwnedString;
    EndIf;
    If CaseNo = 12 Then
        Try SessionParameters.OwnedBoolean = New Array; Result = "assigned";
        Except Result = "error"; EndTry;
        Return Result + ":" + String(SessionParameters.OwnedBoolean);
    EndIf;
    If CaseNo = 13 Then
        Try SessionParameters.OwnedNumber = Undefined; Result = "assigned";
        Except Result = "error"; EndTry;
        Return Result + ":" + String(SessionParameters.OwnedNumber);
    EndIf;
    If CaseNo = 14 Then
        Try Value = SessionParameters.OwnedFailure; Return "value:" + String(Value);
        Except Return "error"; EndTry;
    EndIf;
    If CaseNo = 15 Then Return String(SessionParameters.OwnedWitness); EndIf;
    If CaseNo = 16 Then
        Try Value = SessionParameters.OwnedMissing; Return "value:" + String(Value);
        Except Return "error:" + String(SessionParameters.OwnedMissingCalls); EndTry;
    EndIf;
    Raise "unknown-owned-session-case";
EndFunction

For CaseNo = 1 To 16 Do
    Stage = "setup";
    Try
        Value = ObserveCase(CaseNo,Stage); SessionParameterEmit(CaseNo,Value);
    Except
        SessionParameterDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
