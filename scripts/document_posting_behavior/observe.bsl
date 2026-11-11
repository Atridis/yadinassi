Function TraceOf(Object)
    Trace = ""; Object.AdditionalProperties.Property("Trace", Trace); Return Trace;
EndFunction
Function Snapshot(Reference)
    Q = New Query("SELECT COUNT(*) AS N, SUM(R.Amount) AS Total FROM InformationRegister.OwnedPostingRows AS R WHERE R.Recorder = &Recorder");
    Q.SetParameter("Recorder", Reference); S = Q.Execute().Select(); S.Next();
    Total = 0; If S.Total <> Null Then Total = S.Total; EndIf;
    Return String(S.N) + "," + String(Total);
EndFunction
For CaseNo = 1 To 12 Do
    Failed = False; CancelTrace = ""; Stage = "setup"; OuterTransaction = False;
    Try
        O = Documents.OwnedPostingDoc.CreateDocument(); O.Number = String(CaseNo); O.Date = Date(2024,1,1);
        O.AdditionalProperties.Insert("Trace", ""); O.AdditionalProperties.Insert("Mode", CaseNo);
        If CaseNo = 4 Or CaseNo = 5 Or CaseNo = 6 Or CaseNo = 7 Then
            Stage = "seed";
            O.AdditionalProperties.Insert("Mode",3); O.Write(DocumentWriteMode.Posting);
            O.AdditionalProperties.Insert("Mode",CaseNo); O.AdditionalProperties.Insert("Trace", "");
        EndIf;
        Stage = "write";
        If CaseNo = 12 Then BeginTransaction(); OuterTransaction = True; EndIf;
        Try
            If CaseNo = 1 Or CaseNo = 7 Then O.Write(DocumentWriteMode.Write);
            ElsIf CaseNo = 6 Then O.Write(DocumentWriteMode.UndoPosting);
            Else O.Write(DocumentWriteMode.Posting); EndIf;
        Except
            Failed = True; PostingDiagnostic(CaseNo, Stage, DetailedErrorDescription(ErrorInfo()));
        EndTry;
        If OuterTransaction Then RollbackTransaction(); OuterTransaction = False; EndIf;
        If CaseNo = 10 Then
            CancelTrace = TraceOf(O); O.Number = "101"; O.AdditionalProperties.Insert("Trace", "");
            Try O.Write(DocumentWriteMode.Posting);
            Except Failed = True; PostingDiagnostic(CaseNo, Stage, DetailedErrorDescription(ErrorInfo())); EndTry;
        EndIf;
        Stage = "readback";
        Persisted = O.Ref.GetObject(); PostedValue = "missing";
        If Persisted <> Undefined Then PostedValue = String(Number(Persisted.Posted)); EndIf;
        Stage = "query"; Rows = Snapshot(O.Ref);
        PostingEmit(CaseNo, String(Number(Failed)) + "|" + PostedValue + "|" + Rows + "|" + CancelTrace + TraceOf(O));
    Except
        Details = DetailedErrorDescription(ErrorInfo());
        If OuterTransaction Then RollbackTransaction(); OuterTransaction = False; EndIf;
        PostingDiagnostic(CaseNo, Stage, Details);
    EndTry;
EndDo;
