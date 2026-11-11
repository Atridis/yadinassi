Function Numeric(Value)
    If Value = Null Then Return "null"; EndIf;
    Return Format(Value, "NG=0;NDS=.;NZ=0");
EndFunction
Procedure AddRow(Rows, Item, Warehouse, Amount, Quantity, Period, Expense = False, Active = True, Note = "a")
    Direction = AccumulationRecordType.Receipt;
    If Expense Then Direction = AccumulationRecordType.Expense; EndIf;
    Rows.Add(New Structure("Item,Warehouse,Amount,Quantity,Period,RecordType,Active,Note", Item, Warehouse, Amount, Quantity, Period, Direction, Active, Note));
EndProcedure
Function DocumentOf(NumberValue, Rows, Mode = 0)
    O = Documents.OwnedAccumulationDoc.CreateDocument();
    O.Number = String(NumberValue); O.Date = Date(2024,1,1,12,0,0);
    O.AdditionalProperties.Insert("Rows", Rows); O.AdditionalProperties.Insert("Mode", Mode);
    Return O;
EndFunction
Function TryPost(O, CaseNo, Stage)
    Stage = "write";
    Try O.Write(DocumentWriteMode.Posting); Return "0";
    Except AccumulationDiagnostic(CaseNo, Stage, ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())); Return "1"; EndTry;
EndFunction
Function Raw(Reference)
    Q = New Query("SELECT COUNT(*) AS N, SUM(R.Amount) AS A, SUM(R.Quantity) AS Q FROM AccumulationRegister.OwnedAccumulationRows AS R WHERE R.Recorder=&Recorder");
    Q.SetParameter("Recorder", Reference); S = Q.Execute().Select(); S.Next();
    Return Numeric(S.N) + "," + Numeric(S.A) + "," + Numeric(S.Q);
EndFunction
Function Posted(Reference)
    Q = New Query("SELECT D.Posted AS P FROM Document.OwnedAccumulationDoc AS D WHERE D.Ref=&Recorder");
    Q.SetParameter("Recorder", Reference); S = Q.Execute().Select();
    If Not S.Next() Then Return "missing"; EndIf;
    Return Numeric(Number(S.P));
EndFunction
Function Balance(Item, At)
    Q = New Query("SELECT R.Item AS I, R.Warehouse AS W, R.AmountBalance AS A, R.QuantityBalance AS Q FROM AccumulationRegister.OwnedAccumulationRows.Balance(&At) AS R WHERE R.Item=&Item ORDER BY I,W");
    Q.SetParameter("At", At); Q.SetParameter("Item", Item); S = Q.Execute().Select(); Result = "";
    While S.Next() Do Result = Result + S.I + "," + Numeric(S.W) + "," + Numeric(S.A) + "," + Numeric(S.Q) + ";"; EndDo;
    If Result = "" Then Return "empty"; EndIf;
    Return Result;
EndFunction
Function Turnovers(Item, StartAt, EndAt)
    Q = New Query("SELECT R.Item AS I, R.Warehouse AS W, R.AmountTurnover AS T, R.AmountReceipt AS R, R.AmountExpense AS E, R.QuantityTurnover AS Q FROM AccumulationRegister.OwnedAccumulationRows.Turnovers(&StartAt,&EndAt) AS R WHERE R.Item=&Item ORDER BY I,W");
    Q.SetParameter("StartAt", StartAt); Q.SetParameter("EndAt", EndAt); Q.SetParameter("Item", Item);
    S = Q.Execute().Select(); Result = "";
    While S.Next() Do Result = Result + S.I + "," + Numeric(S.W) + "," + Numeric(S.T) + "," + Numeric(S.R) + "," + Numeric(S.E) + "," + Numeric(S.Q) + ";"; EndDo;
    If Result = "" Then Return "empty"; EndIf;
    Return Result;
EndFunction
Function Qualifiers(Source, Field)
    Q = New Query("SELECT R." + Field + " AS V FROM AccumulationRegister.OwnedAccumulationRows." + Source + " AS R");
    Q.SetParameter("At", Date(2024,1,2)); Q.SetParameter("From", Date(2024,1,1)); Q.SetParameter("To", Date(2024,1,2));
    Table = Q.Execute().Unload(); Description = Table.Columns.Find("V").ValueType;
    N = Description.NumberQualifiers;
    Return Numeric(N.Digits) + "," + Numeric(N.FractionDigits) + "," + Numeric(Number(N.AllowedSign = AllowedSign.Any));
EndFunction
Function ObserveCase(CaseNo, Stage)
    T = Date(2024,1,1,12,0,0); At = Date(2024,1,2); StartAt = Date(2024,1,1);
    Rows = New Array; Item = "c" + String(CaseNo); Stage = "setup";
    If CaseNo = 1 Then
        Stage = "query";
        Return Balance("absent",At) + "|" + Turnovers("absent",StartAt,At) + "|" + Qualifiers("Balance(&At)","AmountBalance") + "|" + Qualifiers("Balance(&At)","QuantityBalance") + "|" + Qualifiers("Turnovers(&From,&To)","AmountTurnover") + "|" + Qualifiers("Turnovers(&From,&To)","AmountReceipt") + "|" + Qualifiers("Turnovers(&From,&To)","AmountExpense");
    ElsIf CaseNo = 2 Or CaseNo = 3 Then
        Item = "shared"; AddRow(Rows,Item,1,2,1,T);
        If CaseNo = 2 Then AddRow(Rows,Item,1,3,2,T); EndIf;
        O = DocumentOf(CaseNo,Rows); Defaults = "";
        If CaseNo = 2 Then
            Set = O.RegisterRecords.OwnedAccumulationRows; R = Set.Add();
            Defaults = Numeric(Number(R.Active)) + "," + Numeric(Number(R.RecordType=AccumulationRecordType.Receipt)) + "," + Numeric(Number(R.Period=Date(1,1,1))) + "," + Numeric(R.LineNumber); Set.Clear();
        EndIf;
        Failed = TryPost(O,CaseNo,Stage); Stage = "query";
        Return Failed + "|" + Defaults + "|" + Raw(O.Ref) + "|" + Balance(Item,At) + "|" + Turnovers(Item,StartAt,At);
    ElsIf CaseNo = 4 Then
        AddRow(Rows,Item,1,10,4,T); AddRow(Rows,Item,1,3,1,T,True);
        AddRow(Rows,Item,1,-2,-0.5,T); AddRow(Rows,Item,1,-1,-0.25,T,True);
    ElsIf CaseNo = 5 Then
        AddRow(Rows,Item,1,7,2,T); AddRow(Rows,Item,1,100,50,T,False,False);
        AddRow(Rows,Item,1,200,70,T,True,False);
    ElsIf CaseNo = 6 Then
        AddRow(Rows,Item,1,1,1,T-1); AddRow(Rows,Item,1,10,10,T); AddRow(Rows,Item,1,100,100,T+1);
    ElsIf CaseNo = 7 Then
        AddRow(Rows,Item,1,1,1,T-1); AddRow(Rows,Item,1,10,10,T);
        AddRow(Rows,Item,1,100,100,T+1); AddRow(Rows,Item,1,1000,1000,T+2); AddRow(Rows,Item,1,10000,10000,T+3);
    ElsIf CaseNo = 8 Then
        AddRow(Rows,Item,1,5,5,T); AddRow(Rows,Item,1,5,5,T,True);
        AddRow(Rows,Item,2,5,7,T); AddRow(Rows,Item,2,5,3,T,True);
    ElsIf CaseNo = 9 Then
        AddRow(Rows,Item,1,60000000.25,1.111,T,False,True,"first");
        AddRow(Rows,Item,1,60000000.25,2.222,T,False,True,"second");
        AddRow(Rows,Item,2,0.25,0.001,T);
    ElsIf CaseNo = 10 Then
        Item = "Case"; AddRow(Rows,Item,1,2,1,T); AddRow(Rows,"case",1,3,2,T);
    Else
        AddRow(Rows,Item,1,5,2,T);
    EndIf;
    O = DocumentOf(CaseNo,Rows,CaseNo); Stage = "seed";
    If CaseNo = 11 Then
        Replacement = New Array; AddRow(Replacement,Item,1,9,3,T); AddRow(Replacement,Item,1,11,4,T);
        O.AdditionalProperties.Insert("Replacement",Replacement);
    EndIf;
    If CaseNo = 16 Then BeginTransaction(); EndIf;
    Failed = TryPost(O,CaseNo,Stage);
    If CaseNo = 16 Then RollbackTransaction(); EndIf;
    Stage = "readback"; State = Posted(O.Ref); RawValue = Raw(O.Ref); Inside = ""; O.AdditionalProperties.Property("Inside",Inside);
    Stage = "query";
    If CaseNo = 6 Then
        Return Failed + "|" + Balance(Item,T-1) + "|" + Balance(Item,T) + "|" + Balance(Item,T+1) + "|" + Balance(Item,T+2);
    ElsIf CaseNo = 7 Then
        Return Failed + "|" + Turnovers(Item,T,T+2) + "|" + Turnovers(Item,T,T);
    ElsIf CaseNo = 12 Then
        Before = RawValue; Extra = New Array; AddRow(Extra,Item,1,7,3,T);
        O.AdditionalProperties.Insert("Rows",Extra); Failed = Failed + TryPost(O,CaseNo,Stage); Same = Raw(O.Ref);
        Fresh = O.Ref.GetObject(); Fresh.AdditionalProperties.Insert("Rows",New Array);
        Failed = Failed + TryPost(Fresh,CaseNo,Stage); Stage = "query";
        Return Failed + "|" + Before + "|" + Same + "|" + Raw(Fresh.Ref) + "|" + Balance(Item,At);
    ElsIf CaseNo = 13 Then
        Stage = "write"; O.Write(DocumentWriteMode.Write); Ordinary = Posted(O.Ref) + "," + Raw(O.Ref);
        O.Write(DocumentWriteMode.UndoPosting); Stage = "query";
        Return Failed + "|" + Ordinary + "|" + Posted(O.Ref) + "," + Raw(O.Ref) + "|" + Balance(Item,At);
    EndIf;
    Return Failed + "|" + State + "|" + RawValue + "|" + Inside + "|" + Balance(Item,At) + "|" + Turnovers(Item,StartAt,At);
EndFunction
For CaseNo = 1 To 16 Do
    Stage = "setup";
    Try
        Value = ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except
        If TransactionActive() Then RollbackTransaction(); EndIf;
        AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
