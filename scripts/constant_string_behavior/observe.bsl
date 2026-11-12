// UNEXECUTED observation. Only a NEW disposable native configuration.
// Existing nonprivileged external-processor harness; exactly one invocation.
Function ObserveConstantString()
    Lines = New Array;
    Lines.Add("witness=constant-string-v1");
    Try
        InitialValue = Constants.OwnedString.Get();
        Lines.Add("initial.get=ok");
        Lines.Add("initial.type=" + String(TypeOf(InitialValue)));
        Lines.Add("initial.is-string=" + String(TypeOf(InitialValue) = Type("String")));
        Lines.Add("initial.is-undefined=" + String(InitialValue = Undefined));
        If TypeOf(InitialValue) = Type("String") Then
            Lines.Add("initial.length=" + String(StrLen(InitialValue)));
            Lines.Add("initial.is-empty=" + String(InitialValue = ""));
        EndIf;
    Except
        Lines.Add("initial.get=error");
        Lines.Add("initial.error=native-operation-failed");
    EndTry;
    Marker = "owned-constant-probe-v1";
    Try
        Constants.OwnedString.Set(Marker);
        Lines.Add("set=ok");
    Except
        Lines.Add("set=error");
        Lines.Add("set.error=native-operation-failed");
    EndTry;
    Try
        ReadBack = Constants.OwnedString.Get();
        Lines.Add("readback.get=ok");
        Lines.Add("readback.type=" + String(TypeOf(ReadBack)));
        Lines.Add("readback.matches-marker=" + String(ReadBack = Marker));
        If TypeOf(ReadBack) = Type("String") Then
            Lines.Add("readback.length=" + String(StrLen(ReadBack)));
        EndIf;
    Except
        Lines.Add("readback.get=error");
        Lines.Add("readback.error=native-operation-failed");
    EndTry;
    Return StrConcat(Lines, Chars.LF);
EndFunction

For CaseNo = 1 To 1 Do
    Stage = "read";
    Value = ObserveConstantString();
    ConstantStringEmit(CaseNo,Value);
EndDo;
