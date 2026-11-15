Function N(Val Value)
    If Value=Null Then Return "null"; EndIf;
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
Function Bound(Text,P,W,StartAt,EndAt)
    Q=New Query(Text); Q.SetParameter("Product",P); Q.SetParameter("Warehouse",W);
    Q.SetParameter("StartAt",StartAt); Q.SetParameter("EndAt",EndAt); Return Q;
EndFunction
Function Rows(Result,Bucket=False)
    S=Result.Select(); V=""; Count=0;
    While S.Next() Do
        Count=Count+1; If Count>32 Then Raise "owned filter row limit"; EndIf;
        If Bucket Then V=V+Format(S.Bucket,"DF=yyyyMMddHHmmss")+","; EndIf;
        V=V+N(S.X)+","+N(S.Y)+";";
    EndDo;
    If V="" Then Return "empty"; EndIf; Return V;
EndFunction
Function Report(Kind,Periodicity,Condition,P,W,StartAt,EndAt)
    Bucket=False; Prefix=""; Ordering="X,Y";
    If Kind="Balance" Then
        Args="&EndAt,"+Condition; Fields="R.QuantityBalance AS X,R.AmountBalance AS Y";
    Else
        Args="&StartAt,&EndAt,"+Periodicity+",";
        If Kind="BalanceAndTurnovers" Then Args=Args+","; Fields="R.QuantityOpeningBalance AS X,R.QuantityClosingBalance AS Y";
        Else Fields="R.QuantityTurnover AS X,R.AmountTurnover AS Y"; EndIf;
        Args=Args+Condition;
        If Periodicity<>"" Then Prefix="R.Period AS Bucket,"; Ordering="Bucket,X,Y"; Bucket=True; EndIf;
    EndIf;
    Q=Bound("SELECT "+Prefix+Fields+" FROM AccumulationRegister.Stock."+Kind+"("+Args+") AS R ORDER BY "+Ordering,P,W,StartAt,EndAt);
    Return Rows(Q.Execute(),Bucket);
EndFunction
Function BlankSlots(Kind,Args,P,W,StartAt,EndAt,Bucket=False)
    If Kind="Balance" Then Fields="R.QuantityBalance AS X,R.AmountBalance AS Y";
    ElsIf Kind="Turnovers" Then Fields="R.QuantityTurnover AS X,R.AmountTurnover AS Y";
    Else Fields="R.QuantityOpeningBalance AS X,R.QuantityClosingBalance AS Y"; EndIf;
    Ordering="X,Y";
    If Bucket Then Fields="R.Period AS Bucket,"+Fields; Ordering="Bucket,X,Y"; EndIf;
    Q=Bound("SELECT "+Fields+" FROM AccumulationRegister.Stock."+Kind+"("+Args+") AS R WHERE R.Product=&Product AND R.Warehouse=&Warehouse ORDER BY "+Ordering,P,W,StartAt,EndAt);
    Return Rows(Q.Execute(),Bucket);
EndFunction
Function ObserveCase(CaseNo,Stage)
    Stage="setup"; Code=String(CaseNo); P=Item("p"+Code); P2=Item("q"+Code); W=Warehouse("w"+Code); W2=Warehouse("v"+Code);
    StartAt=Date(2024,2,1); EndAt=Date(2024,3,31,23,59,59);
    Stage="write";
    D=Move("a"+Code,P,W,Date(2024,1,31),3,6);
    Target=Move("b"+Code,P,W,Date(2024,2,2),5,10);
    D=Move("c"+Code,P,W,Date(2024,3,3),2,4,True);
    D=Move("d"+Code,P,W2,Date(2024,2,2),11,22);
    D=Move("e"+Code,P2,W,Date(2024,2,2),17,34);
    Condition="Product=&Product AND Warehouse=&Warehouse"; Stage="query";
    If CaseNo=1 Then
        Return Report("Balance","","Product=&Product",P,W,StartAt,EndAt)+"|"+Report("Balance","","Warehouse=&Warehouse",P,W,StartAt,EndAt)+"|"+BlankSlots("Balance","&EndAt,",P,W,StartAt,EndAt);
    ElsIf CaseNo=2 Then
        Q=Bound("ВЫБРАТЬ R.QuantityBalance КАК X,R.AmountBalance КАК Y ИЗ РегистрНакопления.Stock.Остатки(&EndAt,Product=&Product И Warehouse=&Warehouse) КАК R",P,W,StartAt,EndAt);
        Return Report("Balance","",Condition,P,W,StartAt,EndAt)+"|"+Rows(Q.Execute());
    ElsIf CaseNo=3 Then Return Report("Turnovers","",Condition,P,W,StartAt,EndAt)+"|"+BlankSlots("Turnovers","&StartAt,&EndAt,",P,W,StartAt,EndAt)+"|"+BlankSlots("Turnovers","&StartAt,&EndAt,,",P,W,StartAt,EndAt);
    ElsIf CaseNo=4 Then Return Report("Turnovers","Day",Condition,P,W,StartAt,EndAt);
    ElsIf CaseNo=5 Then Return Report("Turnovers","Month",Condition,P,W,StartAt,EndAt);
    ElsIf CaseNo=6 Then Return Report("BalanceAndTurnovers","",Condition,P,W,StartAt,EndAt)+"|"+BlankSlots("BalanceAndTurnovers","&StartAt,&EndAt,",P,W,StartAt,EndAt)+"|"+BlankSlots("BalanceAndTurnovers","&StartAt,&EndAt,,",P,W,StartAt,EndAt)+"|"+BlankSlots("BalanceAndTurnovers","&StartAt,&EndAt,,,",P,W,StartAt,EndAt);
    ElsIf CaseNo=7 Then Return Report("BalanceAndTurnovers","Day",Condition,P,W,StartAt,EndAt)+"|"+BlankSlots("BalanceAndTurnovers","&StartAt,&EndAt,Day,,",P,W,StartAt,EndAt,True);
    ElsIf CaseNo=8 Then Return Report("BalanceAndTurnovers","Month",Condition,P,W,StartAt,EndAt);
    ElsIf CaseNo=9 Then
        Empty=Catalogs.Products.EmptyRef(); Missing=Catalogs.Products.GetRef(New UUID("00000000-0000-0000-0000-000000009009"));
        Q=Bound("SELECT R.QuantityTurnover AS X FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,,Product=&Product) AS R",Empty,W,StartAt,EndAt);
        T=Q.Execute().Unload(); C=T.Columns.Find("X"); Typed="false"; If TypeOf(Empty)=Type("CatalogRef.Products") And TypeOf(Missing)=Type("CatalogRef.Products") Then Typed="true"; EndIf;
        Return Report("Balance","",Condition,Empty,W,StartAt,EndAt)+"|"+Report("Turnovers","",Condition,Missing,W,StartAt,EndAt)+"|"+Report("BalanceAndTurnovers","",Condition,Empty,W,StartAt,EndAt)+"|"+N(T.Count())+","+Typed+","+N(C.ValueType.NumberQualifiers.Digits)+","+N(C.ValueType.NumberQualifiers.FractionDigits);
    ElsIf CaseNo=10 Then
        Q=Bound("SELECT SUM(R.QuantityTurnover) AS X,SUM(R.AmountTurnover) AS Y FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,,Product=&Product) AS R WHERE R.QuantityTurnover>0 GROUP BY R.Product",P,W,StartAt,EndAt);
        Return Rows(Q.Execute());
    ElsIf CaseNo=11 Then
        Q=Bound("SELECT A.QuantityBalance AS X,B.QuantityTurnover AS Y FROM AccumulationRegister.Stock.Balance(&EndAt,Product=&Product AND Warehouse=&Warehouse) AS A LEFT JOIN AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,,Product=&Product AND Warehouse=&Warehouse) AS B ON A.Product=B.Product AND A.Warehouse=B.Warehouse",P,W,StartAt,EndAt);
        Joined=Rows(Q.Execute());
        Q=Bound("SELECT D.X AS X,D.Y AS Y FROM (SELECT R.QuantityBalance AS X,R.AmountBalance AS Y FROM AccumulationRegister.Stock.Balance(&EndAt,Product=&Product AND Warehouse=&Warehouse) AS R) AS D",P,W,StartAt,EndAt);
        Derived=Rows(Q.Execute());
        Q=Bound("SELECT R.QuantityBalance AS X,R.AmountBalance AS Y INTO SelectedStock FROM AccumulationRegister.Stock.Balance(&EndAt,Product=&Product AND Warehouse=&Warehouse) AS R; SELECT X,Y FROM SelectedStock",P,W,StartAt,EndAt);
        Batch=Q.ExecuteBatch(); Return Joined+"|"+Derived+"|"+Rows(Batch[1]);
    ElsIf CaseNo=12 Then
        Before=Report("Balance","",Condition,P,W,StartAt,EndAt);
        BeginTransaction();
        Try
            Stage="write"; Added=Move("f"+Code,P,W,Date(2024,2,3),7,14);
            Stage="query"; Inside=Report("Balance","",Condition,P,W,StartAt,EndAt); RollbackTransaction();
        Except RollbackTransaction(); Raise; EndTry;
        After=Report("Balance","",Condition,P,W,StartAt,EndAt);
        Stage="write"; Target.Lines[0].Quantity=19; Target.Write(DocumentWriteMode.Posting);
        Stage="query"; Reposted=Report("Balance","","Warehouse=&Warehouse",P,W,StartAt,EndAt);
        Return Before+"|"+Inside+"|"+After+"|"+Reposted;
    EndIf;
EndFunction
For CaseNo = 1 To 12 Do
    Stage="setup";
    Try Value=ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())); EndTry;
EndDo;
