Function ProbeArray()
    A = New Array;
    A.Add(7);
    A.Add(9);
    Return A;
EndFunction

Procedure ObserveIndex(Val CaseName, Val IndexValue)
    A = ProbeArray();
    Try
        V = A[IndexValue];
        Status = "ok";
    Except
        Status = "error";
    EndTry;
    If Status = "ok" Then
        Status = Status + "|" + ЗначениеВСтрокуВнутр(V);
    EndIf;
    Message("array.bracket-read." + CaseName + ": " + Status);

    A = ProbeArray();
    Try
        V = A.Get(IndexValue);
        Status = "ok";
    Except
        Status = "error";
    EndTry;
    If Status = "ok" Then
        Status = Status + "|" + ЗначениеВСтрокуВнутр(V);
    EndIf;
    Message("array.get." + CaseName + ": " + Status);

    A = ProbeArray();
    Try
        A[IndexValue] = 99;
        Status = "ok";
    Except
        Status = "error";
    EndTry;
    Message("array.bracket-write." + CaseName + ": " + Status
        + "|" + ЗначениеВСтрокуВнутр(A.Count()) + "|" + ЗначениеВСтрокуВнутр(A[0])
        + "|" + ЗначениеВСтрокуВнутр(A[1]));

    A = ProbeArray();
    Try
        A.Set(IndexValue, 99);
        Status = "ok";
    Except
        Status = "error";
    EndTry;
    Message("array.set." + CaseName + ": " + Status
        + "|" + ЗначениеВСтрокуВнутр(A.Count()) + "|" + ЗначениеВСтрокуВнутр(A[0])
        + "|" + ЗначениеВСтрокуВнутр(A[1]));
EndProcedure

ObserveIndex("zero", 0);
ObserveIndex("one", 1);
ObserveIndex("upper", 2);
ObserveIndex("minus-one", -1);
ObserveIndex("minus-half", -0.5);
ObserveIndex("half", 0.5);
ObserveIndex("one-point-nine", 1.9);
ObserveIndex("true", True);
Message("array.indices: complete");
