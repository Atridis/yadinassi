Function ProbeArray(Val Producer)
    If Producer = "split" Then
        Return StrSplit("a,b", ",");
    EndIf;
    A = New Array;
    A.Add("a");
    A.Add("b");
    Return A;
EndFunction

Function ObservationValue(Val V)
    If V = "a" Then
        Return "a";
    ElsIf V = "b" Then
        Return "b";
    ElsIf V = "x" Then
        Return "x";
    EndIf;
    Return "other";
EndFunction

Procedure ObserveProducer(Val Producer)
    A = ProbeArray(Producer);
    Shape = "other";
    If TypeOf(A) = Type("Array") And A.Count() = 2 Then
        Shape = "array|2|" + ObservationValue(A[0]) + "|" + ObservationValue(A[1]);
    EndIf;
    Message("probe." + Producer + ": " + Shape);
EndProcedure

Procedure ObserveIndex(Val Producer, Val CaseName, Val IndexValue, Val Op)
    A = ProbeArray(Producer);
    Status = "ok";
    Try
        If Op = "bracket-read" Then
            V = A[IndexValue];
        ElsIf Op = "get" Then
            V = A.Get(IndexValue);
        ElsIf Op = "get-ru" Then
            V = A.Получить(IndexValue);
        ElsIf Op = "bracket-write" Then
            A[IndexValue] = "x";
        ElsIf Op = "set" Then
            A.Set(IndexValue, "x");
        ElsIf Op = "set-ru" Then
            A.Установить(IndexValue, "x");
        EndIf;
    Except
        Status = "error";
    EndTry;
    If Op = "bracket-read" Or Op = "get" Or Op = "get-ru" Then
        If Status = "ok" Then
            Status = Status + "|" + ObservationValue(V);
        EndIf;
    Else
        If A.Count() = 2 Then
            Status = Status + "|2|" + ObservationValue(A[0]) + "|" + ObservationValue(A[1]);
        Else
            Status = Status + "|changed-count";
        EndIf;
    EndIf;
    Message("probe." + Producer + "." + CaseName + "." + Op + ": " + Status);
EndProcedure

Procedure ObserveCase(Val Producer, Val CaseName, Val IndexValue)
    ObserveIndex(Producer, CaseName, IndexValue, "bracket-read");
    ObserveIndex(Producer, CaseName, IndexValue, "get");
    ObserveIndex(Producer, CaseName, IndexValue, "get-ru");
    ObserveIndex(Producer, CaseName, IndexValue, "bracket-write");
    ObserveIndex(Producer, CaseName, IndexValue, "set");
    ObserveIndex(Producer, CaseName, IndexValue, "set-ru");
EndProcedure

Procedure ObserveAll(Val Producer)
    ObserveProducer(Producer);
    ObserveCase(Producer, "minus-one", -1);
    ObserveCase(Producer, "minus-half", -0.5);
    ObserveCase(Producer, "half", 0.5);
    ObserveCase(Producer, "one-point-nine", 1.9);
    ObserveCase(Producer, "true", True);
    ObserveCase(Producer, "upper", 2);
EndProcedure

ObserveAll("new");
ObserveAll("split");
Message("probe.strsplit-array-indices: complete");
