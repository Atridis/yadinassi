Function N(Val Value)
    If Value=Null Then Return "null"; EndIf;
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Function Item(Val Code)
    O=Catalogs.Products.CreateItem(); O.Code=Code; O.Description="typed"; O.Write(); Return O.Ref;
EndFunction
Function Warehouse(Val Code)
    O=Catalogs.Warehouses.CreateItem(); O.Code=Code; O.Description="typed"; O.Write(); Return O.Ref;
EndFunction
Function Values(Val A,Val B)
    R=New Array; R.Add(A); R.Add(B); Return R;
EndFunction
Function Move(Val Code,Val P,Val W,Val U,Val At,Val Q,Val Batch,Val Grade,Val Reserved,Val LotDate,Val Expense=False)
    If Expense Then D=Documents.Issue.CreateDocument(); Else D=Documents.Receipt.CreateDocument(); EndIf;
    D.Number=Code; D.Date=At; D.Warehouse=W; D.State=Enums.States.Draft;
    L=D.Lines.Add(); L.Product=P; L.Unit=U; L.Quantity=Q; L.Amount=Q*2;
    L.Batch=Batch; L.Grade=Grade; L.Reserved=Reserved; L.LotDate=LotDate;
    D.Write(DocumentWriteMode.Posting); Return D;
EndFunction
Function Bound(Val Text,Val Params)
    Q=New Query(Text);
    For Each Pair In Params Do Q.SetParameter(Pair.Key,Pair.Value); EndDo;
    Return Q;
EndFunction
Function UnitLabel(Val Value)
    If Value=Null Then Return "null"; EndIf;
    If Value=Enums.Units.EmptyRef() Then Return "emptyunit"; EndIf;
    If Value=Enums.Units.Piece Then Return "piece"; EndIf;
    If Value=Enums.Units.Pack Then Return "pack"; EndIf;
    Raise "owned unit label";
EndFunction
Function Rows(Val Result,Val Bucket=False,Val Unit=False)
    S=Result.Select(); V=""; Count=0;
    While S.Next() Do
        Count=Count+1; If Count>32 Then Raise "owned typed filter row limit"; EndIf;
        If Bucket Then V=V+Format(S.Bucket,"DF=yyyyMMddHHmmss")+","; EndIf;
        If Unit Then V=V+UnitLabel(S.U)+","; EndIf;
        V=V+N(S.X)+","+N(S.Y)+";";
    EndDo;
    If V="" Then Return "empty"; EndIf; Return V;
EndFunction
Function Text(Val Kind,Val Periodicity,Val Condition,Val Unit=False)
    Prefix=""; Ordering="X,Y";
    If Kind="Balance" Then
        Args="&EndAt,"+Condition; Fields="R.QuantityBalance AS X,R.AmountBalance AS Y";
    Else
        Args="&StartAt,&EndAt,"+Periodicity+",";
        If Kind="BalanceAndTurnovers" Then Args=Args+","; Fields="R.QuantityOpeningBalance AS X,R.QuantityClosingBalance AS Y";
        Else Fields="R.QuantityTurnover AS X,R.AmountTurnover AS Y"; EndIf;
        Args=Args+Condition;
        If Periodicity<>"" Then Prefix="R.Period AS Bucket,"; Ordering="Bucket,X,Y"; EndIf;
    EndIf;
    If Unit Then Prefix=Prefix+"R.Unit AS U,"; EndIf;
    Return "SELECT "+Prefix+Fields+" FROM AccumulationRegister.Stock."+Kind+"("+Args+") AS R ORDER BY "+Ordering;
EndFunction
Function Report(Val Kind,Val Periodicity,Val Condition,Val Params,Val Unit=False)
    Q=Bound(Text(Kind,Periodicity,Condition,Unit),Params);
    Return Rows(Q.Execute(),Periodicity<>"",Unit);
EndFunction
Function Control(Val Kind,Val Condition,Val Params)
    Q=Bound(Text(Kind,"",Condition),Params);
    Try R=Q.Execute(); Except Return "execute-refused"; EndTry;
    Return Rows(R);
EndFunction
Function Trio(Val Condition,Val Params)
    Return Report("Balance","",Condition,Params)+"|"+Report("Turnovers","",Condition,Params)+"|"+Report("BalanceAndTurnovers","",Condition,Params);
EndFunction
Function ObserveCase(CaseNo,Stage)
    Stage="setup"; Code=String(CaseNo); P=Item("p"+Code); P2=Item("q"+Code); W=Warehouse("w"+Code); W2=Warehouse("v"+Code);
    U=Enums.Units.Piece; U2=Enums.Units.Pack; LotDate=Date(2024,2,1);
    Params=New Structure; Params.Insert("Product",P); Params.Insert("Warehouse",W); Params.Insert("Unit",U);
    Params.Insert("StartAt",Date(2024,2,1)); Params.Insert("EndAt",Date(2024,3,31,23,59,59));
    Params.Insert("Batch","lot"); Params.Insert("Grade",1.25); Params.Insert("Reserved",True); Params.Insert("LotDate",LotDate);
    Params.Insert("Products",Values(P,P2)); Params.Insert("Units",Values(U,U2));
    Stage="write";
    D=Move("a"+Code,P,W,U,Date(2024,1,31),3,"lot",1.25,True,LotDate);
    Target=Move("b"+Code,P,W,U,Date(2024,2,2),5,"lot",1.25,True,LotDate);
    D=Move("c"+Code,P,W,U,Date(2024,3,3),2,"lot",1.25,True,LotDate,True);
    D=Move("d"+Code,P,W2,U,Date(2024,2,2),11,"LOT",2.5,False,Date(2024,2,2));
    D=Move("e"+Code,P2,W,U2,Date(2024,2,2),17,"lot",1.25,True,LotDate);
    D=Move("f"+Code,P,W,U2,Date(2024,2,3),7,"lot",1.25,True,LotDate);
    D=Move("g"+Code,P,W,Enums.Units.EmptyRef(),Date(2024,2,4),13,"",0,False,LotDate);
    D=Move("h"+Code,P,W,U,Date(2024,2,5),19,"café",1.25,True,LotDate);
    D=Move("i"+Code,P,W,U,Date(2024,2,6),23,"lot ",1.25,True,LotDate);
    Prefix="Product=&Product AND "; Stage="query";
    If CaseNo=1 Then
        V=Report("Balance","",Prefix+"Batch=&Batch",Params)+"|"+Report("Balance","",Prefix+"Grade=&Grade",Params)+"|"+Report("Balance","",Prefix+"Reserved=&Reserved",Params)+"|"+Report("Balance","",Prefix+"LotDate=&LotDate",Params);
        Params.Batch="LOT"; V=V+"|"+Report("Balance","",Prefix+"Batch=&Batch",Params);
        Params.Batch="café"; V=V+"|"+Report("Balance","",Prefix+"Batch=&Batch",Params);
        Params.Batch="lot "; V=V+"|"+Report("Balance","",Prefix+"Batch=&Batch",Params);
        Params.Batch="longer-than-thirty-two-character-field-value"; V=V+"|"+Report("Balance","",Prefix+"Batch=&Batch",Params);
        Params.Grade=1.251; Return V+"|"+Report("Balance","",Prefix+"Grade=&Grade",Params);
    ElsIf CaseNo=2 Then
        Params.Insert("Batches",Values("lot","lot")); Params.Insert("Grades",Values(1.25,0));
        Params.Insert("Flags",Values(True,False)); Params.Insert("Dates",Values(LotDate,Date(2024,2,2)));
        Return Report("Turnovers","",Prefix+"Batch IN (&Batches)",Params)+"|"+Report("Turnovers","",Prefix+"Grade IN (&Grades)",Params)+"|"+Report("Turnovers","",Prefix+"Reserved IN (&Flags)",Params)+"|"+Report("Turnovers","",Prefix+"LotDate IN (&Dates)",Params)+"|"+Report("Turnovers","",Prefix+"Grade IN (&Grades) AND Reserved=&Reserved",Params);
    ElsIf CaseNo=3 Then
        Return Report("Balance","","Product=&Product",Params)+"|"+Report("Balance","","Warehouse=&Warehouse AND Unit=&Unit",Params)+"|"+Report("Balance","",Prefix+"Warehouse=&Warehouse AND Unit=&Unit",Params,True);
    ElsIf CaseNo=4 Then
        C="Warehouse=&Warehouse AND Product IN (&Products) AND Unit IN (&Units)";
        V=Control("Turnovers",C,Params)+"|"+Control("Turnovers","Warehouse=&Warehouse AND Product IN &Products AND Unit IN &Units",Params);
        Params.Products=New FixedArray(Params.Products); Params.Units=New FixedArray(Params.Units);
        Return V+"|"+Control("Turnovers",C,Params)+"|"+Control("Turnovers","Warehouse=&Warehouse AND Product IN &Products AND Unit IN &Units",Params);
    ElsIf CaseNo=5 Then
        Return Trio("Product IN (&Products) AND Unit IN (&Units) AND Warehouse=&Warehouse AND Grade=&Grade AND Reserved=&Reserved",Params);
    ElsIf CaseNo=6 Then
        C="Product IN (&Products) AND Unit IN (&Units) AND Warehouse=&Warehouse AND Batch=&Batch";
        Return Report("Turnovers","Day",C,Params)+"|"+Report("BalanceAndTurnovers","Day",C,Params);
    ElsIf CaseNo=7 Then
        C="Product IN (&Products) AND Unit IN (&Units) AND Warehouse=&Warehouse AND Batch=&Batch";
        Return Report("Turnovers","Month",C,Params)+"|"+Report("BalanceAndTurnovers","Month",C,Params);
    ElsIf CaseNo=8 Then
        Params.Product=Catalogs.Products.EmptyRef(); V=Trio("Product=&Product AND Warehouse=&Warehouse",Params);
        Params.Product=Catalogs.Products.GetRef(New UUID("00000000-0000-0000-0000-000000009009"));
        V=V+"|"+Report("Balance","","Product=&Product",Params)+"|"+Report("Balance","","Product=&Product",Params,True);
        Params.Product=P; Params.Unit=Enums.Units.EmptyRef(); Params.Units=Values(Params.Unit,Params.Unit);
        Return V+"|"+Trio(Prefix+"Unit=&Unit",Params)+"|"+Report("Balance","",Prefix+"Unit IN (&Units)",Params,True);
    ElsIf CaseNo=9 Then
        Params.Units=New Array; V=Trio(Prefix+"Unit IN (&Units)",Params);
        Params.Units.Add(Null); V=V+"|"+Trio(Prefix+"Unit IN (&Units)",Params);
        Params.Units.Add(U); Return V+"|"+Trio(Prefix+"Unit IN (&Units)",Params);
    ElsIf CaseNo=10 Then
        Params.Grade="1.25"; V=Control("Balance",Prefix+"Grade=&Grade",Params);
        Params.Unit=Enums.States.Draft; V=V+"|"+Control("Balance",Prefix+"Unit=&Unit",Params);
        Params.Units=Values(Enums.States.Draft,Enums.States.Approved); V=V+"|"+Control("Balance",Prefix+"Unit IN (&Units)",Params);
        Params.Units=Values(U,Enums.States.Draft); Return V+"|"+Control("Balance",Prefix+"Unit IN (&Units)",Params);
    ElsIf CaseNo=11 Then
        C=Prefix+"Warehouse=&Warehouse AND Unit IN (&Units)";
        V=Report("Balance","",C,Params)+"|"+Report("Balance","",C,Params,True);
        Q=Bound("SELECT R.QuantityBalance AS X,R.AmountBalance AS Y FROM AccumulationRegister.Stock.Balance(&EndAt,"+C+") AS R WHERE R.Unit=&Unit ORDER BY X,Y",Params); V=V+"|"+Rows(Q.Execute());
        Q=Bound("SELECT SUM(R.QuantityTurnover) AS X,SUM(R.AmountTurnover) AS Y FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,,"+C+") AS R GROUP BY R.Unit HAVING SUM(R.QuantityTurnover)>0 ORDER BY X,Y",Params); V=V+"|"+Rows(Q.Execute());
        Params.Insert("Missing",Catalogs.Products.GetRef(New UUID("00000000-0000-0000-0000-000000009009")));
        Q=Bound("SELECT A.QuantityBalance AS X,B.QuantityTurnover AS Y FROM AccumulationRegister.Stock.Balance(&EndAt,"+C+") AS A LEFT JOIN AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,,Product=&Missing AND Unit IN (&Units)) AS B ON A.Unit=B.Unit ORDER BY X,Y",Params);
        Return V+"|"+Rows(Q.Execute());
    ElsIf CaseNo=12 Then
        C=Prefix+"Warehouse=&Warehouse AND Unit IN (&Units)"; Params.Units=Values(U,U);
        Before=Report("Balance","",C,Params); BeginTransaction();
        Try
            Stage="write"; D=Move("z"+Code,P,W,U,Date(2024,2,7),29,"lot",1.25,True,LotDate);
            Stage="query"; Inside=Report("Balance","",C,Params); RollbackTransaction();
        Except RollbackTransaction(); Raise; EndTry;
        After=Report("Balance","",C,Params); Stage="write";
        Target.Lines[0].Quantity=31; Target.Write(DocumentWriteMode.Posting); Stage="query";
        Q=Bound(Text("Balance","",C),Params); First=Rows(Q.Execute()); Params.Units.Add(U2); Second=Rows(Q.Execute());
        Return Before+"|"+Inside+"|"+After+"|"+First+"|"+Second;
    EndIf;
EndFunction
For CaseNo = 1 To 12 Do
    Stage="setup";
    Try Value=ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())); EndTry;
EndDo;
