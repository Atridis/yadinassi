Function N(Val Value)
    If Value = Null Then Return "null"; EndIf;
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Function Item(Code)
    O=Catalogs.Products.CreateItem(); O.Code=Code; O.Description="same"; O.Write(); Return O.Ref;
EndFunction
Function Warehouse(Code)
    O=Catalogs.Warehouses.CreateItem(); O.Code=Code; O.Description="same"; O.Write(); Return O.Ref;
EndFunction
Function Move(Code,P,W,At,Q,A,Expense=False)
    If Expense Then D=Documents.Issue.CreateDocument(); Else D=Documents.Receipt.CreateDocument(); EndIf;
    D.Number=Code; D.Date=At; D.Warehouse=W;
    L=D.Lines.Add(); L.Product=P; L.Quantity=Q; L.Amount=A;
    D.Write(DocumentWriteMode.Posting); Return D;
EndFunction
Function Statement(P,StartAt,EndAt,Periodicity="",Flows=False)
    If Flows Then
        Table="Turnovers";
        Fields="R.QuantityTurnover AS T,R.QuantityReceipt AS R,R.QuantityExpense AS E,R.AmountTurnover AS A";
    Else
        Table="BalanceAndTurnovers";
        Fields="R.QuantityOpeningBalance AS O,R.QuantityReceipt AS R,R.QuantityExpense AS E,R.QuantityTurnover AS T,R.QuantityClosingBalance AS C,R.AmountOpeningBalance AS AO,R.AmountReceipt AS AR,R.AmountExpense AS AE,R.AmountTurnover AS AT,R.AmountClosingBalance AS AC";
    EndIf;
    Arguments="&StartAt,&EndAt"; Prefix=""; Ordering="P,W";
    If Periodicity<>"" Then Arguments=Arguments+","+Periodicity; Prefix="R.Period AS Bucket,"; Ordering="Bucket,P,W"; EndIf;
    Q=New Query("SELECT "+Prefix+"P.Code AS P,W.Code AS W,"+Fields+" FROM AccumulationRegister.Stock."+Table+"("+Arguments+") AS R INNER JOIN Catalog.Products AS P ON R.Product=P.Ref INNER JOIN Catalog.Warehouses AS W ON R.Warehouse=W.Ref WHERE R.Product=&Product ORDER BY "+Ordering);
    Q.SetParameter("StartAt",StartAt); Q.SetParameter("EndAt",EndAt); Q.SetParameter("Product",P);
    S=Q.Execute().Select(); V=""; Count=0;
    While S.Next() Do
        Count=Count+1; If Count>32 Then Raise "owned period row limit"; EndIf;
        If Periodicity<>"" Then V=V+Format(S.Bucket,"DF=yyyyMMddHHmmss")+","; EndIf;
        V=V+S.P+","+S.W+",";
        If Flows Then V=V+N(S.T)+","+N(S.R)+","+N(S.E)+","+N(S.A)+";";
        Else V=V+N(S.O)+","+N(S.R)+","+N(S.E)+","+N(S.T)+","+N(S.C)+","+N(S.AO)+","+N(S.AR)+","+N(S.AE)+","+N(S.AT)+","+N(S.AC)+";"; EndIf;
    EndDo;
    If V="" Then Return "empty"; EndIf; Return V;
EndFunction
Function ObserveCase(CaseNo,Stage)
    Stage="setup"; Code=String(CaseNo); P=Item("p"+Code); W=Warehouse("w"+Code);
    StartAt=Date(2024,2,1); EndAt=Date(2024,2,29,23,59,59); Stage="write";
    If CaseNo=1 Then
        Q=New Query("SELECT R.QuantityOpeningBalance AS O,R.QuantityReceipt AS R,R.QuantityExpense AS E,R.QuantityTurnover AS T,R.QuantityClosingBalance AS C,R.AmountOpeningBalance AS AO,R.AmountReceipt AS AR,R.AmountExpense AS AE,R.AmountTurnover AS AT,R.AmountClosingBalance AS AC FROM AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt) AS R WHERE R.Product=&Product");
        Q.SetParameter("StartAt",StartAt); Q.SetParameter("EndAt",EndAt); Q.SetParameter("Product",P); Result=Q.Execute();
        V=""; For Each Column In Result.Unload().Columns Do V=V+Column.Name+","+N(Column.ValueType.NumberQualifiers.Digits)+","+N(Column.ValueType.NumberQualifiers.FractionDigits)+";"; EndDo;
        Return V+"|"+Statement(P,StartAt,EndAt);
    ElsIf CaseNo=2 Then
        D=Move(Code,P,W,Date(2024,1,31,23,59,59),5,10);
    ElsIf CaseNo=3 Then
        D=Move(Code,P,W,StartAt,5,10);
    ElsIf CaseNo=4 Then
        D=Move(Code,P,W,EndAt,5,10);
    ElsIf CaseNo=5 Then
        D=Move("a"+Code,P,W,StartAt-1,3,6); D=Move("b"+Code,P,W,StartAt,5,10); D=Move("c"+Code,P,W,EndAt+1,7,14);
        Stage="query"; Return Statement(P,StartAt,EndAt)+"|"+Statement(P,StartAt,StartAt);
    ElsIf CaseNo=6 Then
        D=Move("a"+Code,P,W,StartAt,5,10); D=Move("b"+Code,P,W,StartAt,5,10,True);
        P2=Item("q"+Code); D=Move("c"+Code,P2,W,StartAt,0,0);
        Stage="query"; Return Statement(P,StartAt,EndAt)+"|"+Statement(P2,StartAt,EndAt);
    ElsIf CaseNo=7 Then
        D=Move("a"+Code,P,W,StartAt,1.25,-2.50); D=Move("b"+Code,P,W,StartAt,1.25,1.25,True);
    ElsIf CaseNo=8 Then
        P2=Item("q"+Code); W2=Warehouse("v"+Code); D=Move("a"+Code,P,W,StartAt,5,10); D=Move("b"+Code,P2,W2,StartAt,7,14);
        Before=Statement(P,StartAt,EndAt)+"|"+Statement(P2,StartAt,EndAt); C=P.GetObject(); C.Description="renamed"; C.Write();
        Stage="query"; Return Before+"|"+Statement(P,StartAt,EndAt)+"|"+Statement(P2,StartAt,EndAt);
    ElsIf CaseNo=9 Then
        StartAt=Date(2024,2,1,12,0,0); EndAt=Date(2024,2,3,12,0,0);
        D=Move("a"+Code,P,W,StartAt-1,3,6); D=Move("b"+Code,P,W,StartAt,5,10); D=Move("c"+Code,P,W,Date(2024,2,1,18,0,0),2,4,True); D=Move("d"+Code,P,W,EndAt,1,2,True);
        Stage="query"; Return Statement(P,StartAt,EndAt,"Day")+"|"+Statement(P,StartAt,EndAt,"Day",True);
    ElsIf CaseNo=10 Then
        StartAt=Date(2023,12,15,12,0,0); EndAt=Date(2024,3,2,12,0,0);
        D=Move("a"+Code,P,W,StartAt-1,3,6); D=Move("b"+Code,P,W,StartAt,5,10); D=Move("c"+Code,P,W,Date(2024,1,1),2,4,True); D=Move("d"+Code,P,W,Date(2024,2,29,23,59,59),1,2,True); D=Move("e"+Code,P,W,EndAt,1,2);
        Stage="query"; Return Statement(P,StartAt,EndAt,"Month")+"|"+Statement(P,StartAt,EndAt,"Month",True);
    ElsIf CaseNo=11 Then
        StartAt=Date(2024,1,1); EndAt=Date(2024,4,30,23,59,59);
        D=Move("a"+Code,P,W,StartAt-1,3,6); D=Move("b"+Code,P,W,Date(2024,3,1),2,4);
        P2=Item("q"+Code); D=Move("c"+Code,P2,W,StartAt-1,7,14);
        Stage="query"; Return Statement(P,StartAt,EndAt,"Month")+"|"+Statement(P2,StartAt,EndAt,"Month")+"|"+Statement(P2,Date(2024,2,1),Date(2024,2,3),"Day");
    ElsIf CaseNo=12 Then
        D=Move(Code,P,W,StartAt,5,10); Before=Statement(P,StartAt,EndAt); D.Lines[0].Quantity=7; D.Write(DocumentWriteMode.Posting); Reposted=Statement(P,StartAt,EndAt); D.Write(DocumentWriteMode.UndoPosting);
        Stage="query"; Return Before+"|"+Reposted+"|"+Statement(P,StartAt,EndAt);
    ElsIf CaseNo=13 Then
        BeginTransaction();
        Try P2=Item("q"+Code); D=Move(Code,P2,W,StartAt,5,10); Inside=Statement(P2,StartAt,EndAt); RollbackTransaction(); Except RollbackTransaction(); Raise; EndTry;
        Stage="query"; Return Inside+"|"+Statement(P2,StartAt,EndAt);
    ElsIf CaseNo=14 Then
        StartAt=Date(9999,12,31); EndAt=Date(9999,12,31,23,59,59); D=Move(Code,P,W,EndAt,5,10);
        Stage="query"; Return Statement(P,StartAt,EndAt)+"|"+Statement(P,StartAt,EndAt,"Day")+"|"+Statement(P,StartAt,EndAt,"Month");
    EndIf;
    Stage="query"; Return Statement(P,StartAt,EndAt);
EndFunction
For CaseNo = 1 To 14 Do
    Stage="setup";
    Try Value=ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())); EndTry;
EndDo;
