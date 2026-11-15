// Independent direct enum relational observations; no authored expected output.
Function N(Val Value)
    If Value=Null Then Return "null"; EndIf;
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Function E(Val Value)
    If Value=Null Then Return "null"; EndIf;
    If TypeOf(Value)=Type("EnumRef.Units") Then
        If Value=Enums.Units.EmptyRef() Then Return "unit-empty"; EndIf;
        If Value=Enums.Units.Piece Then Return "unit-piece"; EndIf;
        If Value=Enums.Units.Pack Then Return "unit-pack"; EndIf;
    ElsIf TypeOf(Value)=Type("EnumRef.States") Then
        If Value=Enums.States.EmptyRef() Then Return "state-empty"; EndIf;
        If Value=Enums.States.Draft Then Return "state-draft"; EndIf;
        If Value=Enums.States.Approved Then Return "state-approved"; EndIf;
    ElsIf TypeOf(Value)=Type("String") And Value="owned" Then Return "string-owned";
    ElsIf TypeOf(Value)=Type("Number") Then Return "number-"+N(Value);
    EndIf;
    Raise "owned relational value label";
EndFunction
Function Values(Val A,Val B)
    Result=New Array; Result.Add(A); Result.Add(B); Return Result;
EndFunction
Function Item(Val Code,Val Unit)
    O=Catalogs.Products.CreateItem(); O.Code=Code; O.Description="relational"; O.Unit=Unit; O.Write(); Return O.Ref;
EndFunction
Function Warehouse(Val Code)
    O=Catalogs.Warehouses.CreateItem(); O.Code=Code; O.Description="relational"; O.Write(); Return O.Ref;
EndFunction
Function Move(Val Code,Val P,Val W,Val U,Val At,Val Q,Val Expense=False)
    If Expense Then D=Documents.Issue.CreateDocument(); Else D=Documents.Receipt.CreateDocument(); EndIf;
    D.Number=Code; D.Date=At; D.Warehouse=W; D.State=Enums.States.Approved;
    L=D.Lines.Add(); L.Product=P; L.Unit=U; L.Quantity=Q; L.Amount=Q*2;
    D.Write(DocumentWriteMode.Posting); Return D;
EndFunction
Function Bound(Val Text,Val Params)
    Q=New Query(Text); For Each Pair In Params Do Q.SetParameter(Pair.Key,Pair.Value); EndDo; Return Q;
EndFunction
Function Rows(Val Result)
    // Normalize only emitted ASCII tokens, not Query enum ordering semantics.
    S=Result.Select(); Tokens=New Array;
    While S.Next() Do
        If Tokens.Count()>=32 Then Raise "owned relational row limit"; EndIf;
        Token=E(S.U)+","+N(S.X)+";"; Index=0;
        While Index<Tokens.Count() Do
            If Tokens[Index]>Token Then Break; EndIf; Index=Index+1;
        EndDo;
        Tokens.Insert(Index,Token);
    EndDo;
    If Tokens.Count()=0 Then Return "empty"; EndIf;
    ResultText=""; For Each Token In Tokens Do ResultText=ResultText+Token; EndDo; Return ResultText;
EndFunction
Function Report(Val Text,Val Params)
    Return Rows(Bound(Text,Params).Execute());
EndFunction
Function Control(Val Text,Val Params)
    Q=Bound(Text,Params);
    Try R=Q.Execute(); Except Return "execute-refused"; EndTry;
    Return Rows(R);
EndFunction
Function CatalogRows(Val Condition)
    Return "SELECT P.Unit AS U,1 AS X FROM Catalog.Products AS P WHERE (P.Ref=&Product OR P.Ref=&OtherProduct OR P.Ref=&EmptyProduct) AND "+Condition;
EndFunction
Function NullableRows(Val Condition)
    Return "SELECT R.Unit AS U,1 AS X FROM Catalog.Products AS P LEFT JOIN AccumulationRegister.Stock AS R ON R.Product=P.Ref AND R.Warehouse=&Warehouse WHERE P.Ref=&EmptyProduct AND "+Condition;
EndFunction
Function BalanceRows()
    Return "SELECT T.Unit AS U,SUM(T.Quantity) AS X FROM (SELECT R.Unit AS Unit,R.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&EndAt,Product=&Product AND Warehouse=&Warehouse) AS R) AS T WHERE T.Unit IN (&Units) GROUP BY T.Unit";
EndFunction
Function ObserveCase(CaseNo,Stage)
    Stage="setup"; Code=String(CaseNo); U=Enums.Units.Piece; U2=Enums.Units.Pack; UE=Enums.Units.EmptyRef();
    P=Item("rp"+Code,U); P2=Item("rq"+Code,U2); P0=Item("re"+Code,UE); W=Warehouse("rw"+Code);
    Params=New Structure; Params.Insert("Product",P); Params.Insert("OtherProduct",P2); Params.Insert("EmptyProduct",P0);
    Params.Insert("Warehouse",W); Params.Insert("Unit",U); Params.Insert("OtherUnit",U2); Params.Insert("EmptyUnit",UE);
    Params.Insert("State",Enums.States.Draft); Params.Insert("StartAt",Date(2024,1,1)); Params.Insert("EndAt",Date(2024,3,31,23,59,59));
    Params.Insert("Units",Values(U,U)); Params.Insert("One",U); Params.Insert("NullValue",Null);
    Stage="write";
    D=Move("ra"+Code,P,W,U,Date(2024,1,1),3); Target=Move("rb"+Code,P,W,U,Date(2024,2,2),5);
    D=Move("rc"+Code,P,W,U2,Date(2024,2,3),7); D=Move("rd"+Code,P,W,UE,Date(2024,2,4),11);
    D=Move("re"+Code,P2,W,U2,Date(2024,2,4),13); D=Move("rf"+Code,P,W,U,Date(2024,2,5),2,True);
    Stage="query";
    If CaseNo=1 Then
        V=Report(CatalogRows("P.Unit=&Unit"),Params)+"|"+Control(CatalogRows("P.Unit IN (&One)"),Params);
        V=V+"|"+Control(CatalogRows("P.Unit IN (&Units)"),Params)+"|"+Control(CatalogRows("P.Unit IN &Units"),Params);
        Params.Units=New FixedArray(Params.Units);
        Return V+"|"+Control(CatalogRows("P.Unit IN (&Units)"),Params)+"|"+Control(CatalogRows("P.Unit IN &Units"),Params);
    ElsIf CaseNo=2 Then
        Params.Units=New Array; V="";
        For Variant=1 To 5 Do
            If Variant=2 Then Params.Units.Add(Null);
            ElsIf Variant=3 Then Params.Units.Add(U);
            ElsIf Variant=4 Then Params.Units.Add(U);
            ElsIf Variant=5 Then Params.Units=Values(UE,Null); EndIf;
            If V<>"" Then V=V+"|"; EndIf;
            V=V+Report(CatalogRows("P.Unit IN (&Units)"),Params)+"|"+Report(CatalogRows("P.Unit NOT IN (&Units)"),Params);
            V=V+"|"+Report(NullableRows("R.Unit IN (&Units)"),Params)+"|"+Report(NullableRows("R.Unit NOT IN (&Units)"),Params);
        EndDo;
        Return V;
    ElsIf CaseNo=3 Then
        Params.Units=Values(Enums.States.Draft,Enums.States.Approved); V=Control(CatalogRows("P.Unit IN (&Units)"),Params)+"|"+Control(CatalogRows("P.Unit NOT IN (&Units)"),Params);
        Params.Units=Values(U,Enums.States.Draft); V=V+"|"+Control(CatalogRows("P.Unit IN (&Units)"),Params)+"|"+Control(CatalogRows("P.Unit NOT IN (&Units)"),Params);
        Params.Units=Values("owned",1); V=V+"|"+Control(CatalogRows("P.Unit IN (&Units)"),Params);
        Params.Units=Values(U,"owned"); V=V+"|"+Control(CatalogRows("P.Unit IN (&Units)"),Params);
        Params.One=Enums.States.Draft; Return V+"|"+Control(CatalogRows("P.Unit IN (&One)"),Params);
    ElsIf CaseNo=4 Then
        Params.Units=Values(U,Null);
        V=Report(CatalogRows("P.Unit IN (&Units)"),Params);
        V=V+"|"+Report("SELECT R.Unit AS U,COUNT(*) AS X FROM Catalog.Products AS P LEFT JOIN AccumulationRegister.Stock AS R ON R.Product=P.Ref AND R.Warehouse=&Warehouse AND R.Unit IN (&Units) WHERE P.Ref=&Product OR P.Ref=&EmptyProduct GROUP BY R.Unit",Params);
        V=V+"|"+Report("SELECT R.Unit AS U,SUM(R.Quantity) AS X FROM AccumulationRegister.Stock AS R WHERE R.Product=&Product AND R.Warehouse=&Warehouse GROUP BY R.Unit HAVING R.Unit IN (&Units)",Params);
        Return V+"|"+Report("SELECT P.Unit AS U,CASE WHEN P.Unit IN (&Units) THEN 1 WHEN P.Unit NOT IN (&Units) THEN 2 ELSE 3 END AS X FROM Catalog.Products AS P WHERE P.Ref=&Product OR P.Ref=&OtherProduct OR P.Ref=&EmptyProduct",Params);
    ElsIf CaseNo=5 Then
        V=Report("SELECT CASE WHEN P.Unit=&Unit THEN P.Unit ELSE &OtherUnit END AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product OR P.Ref=&EmptyProduct",Params);
        V=V+"|"+Report("SELECT CASE WHEN P.Unit=&Unit THEN P.Unit END AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product OR P.Ref=&EmptyProduct",Params);
        V=V+"|"+Report("SELECT ISNULL(R.Unit,P.Unit) AS U,1 AS X FROM Catalog.Products AS P LEFT JOIN AccumulationRegister.Stock AS R ON R.Product=P.Ref AND R.Warehouse=&Warehouse WHERE P.Ref=&EmptyProduct",Params);
        V=V+"|"+Report("SELECT ISNULL(P.Unit,&OtherUnit) AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&EmptyProduct",Params);
        Return V+"|"+Report("SELECT ISNULL(NULL,&Unit) AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product",Params);
    ElsIf CaseNo=6 Then
        V=Control("SELECT CASE WHEN P.Ref=&Product THEN P.Unit ELSE &State END AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product OR P.Ref=&OtherProduct",Params);
        V=V+"|"+Control("SELECT CASE WHEN P.Ref=&Product THEN P.Unit ELSE 5 END AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product",Params);
        V=V+"|"+Control("SELECT ISNULL(P.Unit,&State) AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product",Params);
        V=V+"|"+Control("SELECT ISNULL(NULL,&State) AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product",Params);
        Return V+"|"+Control("SELECT CASE WHEN P.Ref=&Product THEN P.Unit ELSE &State END AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product AND P.Ref=&OtherProduct",Params);
    ElsIf CaseNo=7 Then
        Inner="SELECT P.Unit AS Unit FROM Catalog.Products AS P WHERE P.Ref=&Product OR P.Ref=&OtherProduct OR P.Ref=&EmptyProduct";
        V=Report("SELECT T.Unit AS U,COUNT(*) AS X FROM ("+Inner+") AS T GROUP BY T.Unit",Params);
        V=V+"|"+Report("SELECT DISTINCT T.Unit AS U,1 AS X FROM ("+Inner+") AS T WHERE T.Unit=&Unit",Params);
        V=V+"|"+Report("SELECT &Unit AS U,COUNT(DISTINCT T.Unit) AS X FROM ("+Inner+") AS T",Params);
        Empty="SELECT P.Unit AS Unit FROM Catalog.Products AS P WHERE P.Ref=&Product AND P.Ref=&OtherProduct";
        V=V+"|"+Report("SELECT T.Unit AS U,1 AS X FROM ("+Empty+") AS T",Params);
        Return V+"|"+Report("SELECT B.Unit AS U,1 AS X FROM ("+Inner+") AS A LEFT JOIN ("+Empty+") AS B ON A.Unit=B.Unit",Params);
    ElsIf CaseNo=8 Then
        Sub="SELECT R.Unit FROM AccumulationRegister.Stock AS R WHERE R.Product=&Product AND R.Warehouse=&Warehouse";
        V=Report(CatalogRows("P.Unit IN ("+Sub+")"),Params)+"|"+Report(CatalogRows("P.Unit NOT IN ("+Sub+")"),Params);
        Empty="SELECT R.Unit FROM AccumulationRegister.Stock AS R WHERE R.Product=&EmptyProduct AND R.Warehouse=&Warehouse";
        V=V+"|"+Report(CatalogRows("P.Unit IN ("+Empty+")"),Params)+"|"+Report(CatalogRows("P.Unit NOT IN ("+Empty+")"),Params);
        WithNull="SELECT R.Unit FROM Catalog.Products AS P LEFT JOIN AccumulationRegister.Stock AS R ON R.Product=P.Ref AND R.Warehouse=&Warehouse WHERE P.Ref=&EmptyProduct";
        V=V+"|"+Report(CatalogRows("P.Unit IN ("+WithNull+")"),Params)+"|"+Report(CatalogRows("P.Unit NOT IN ("+WithNull+")"),Params);
        V=V+"|"+Report(CatalogRows("P.Unit IN ("+Sub+" UNION ALL "+WithNull+")"),Params);
        Wrong="SELECT R.State FROM AccumulationRegister.Stock AS R WHERE R.Product=&Product AND R.Warehouse=&Warehouse";
        Return V+"|"+Control(CatalogRows("P.Unit IN ("+Wrong+")"),Params);
    ElsIf CaseNo=9 Then
        A="SELECT P.Unit AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product OR P.Ref=&EmptyProduct";
        V=Report(A+" UNION "+A,Params)+"|"+Report(A+" UNION ALL "+A,Params);
        B="SELECT NULL AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product";
        V=V+"|"+Report(A+" UNION "+B,Params);
        Empty="SELECT P.Unit AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product AND P.Ref=&OtherProduct";
        V=V+"|"+Report(Empty+" UNION ALL "+A,Params);
        Wrong="SELECT &State AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product";
        V=V+"|"+Control(A+" UNION ALL "+Wrong,Params);
        WrongEmpty="SELECT &State AS U,1 AS X FROM Catalog.Products AS P WHERE P.Ref=&Product AND P.Ref=&OtherProduct";
        Return V+"|"+Control(Empty+" UNION ALL "+WrongEmpty,Params);
    ElsIf CaseNo=10 Then
        Params.Units=Values(U,U2); V=Report(BalanceRows(),Params);
        A="SELECT R.Unit AS Unit,R.QuantityTurnover AS Quantity FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,,Product=&Product AND Warehouse=&Warehouse AND Unit IN (&Units)) AS R";
        V=V+"|"+Report("SELECT T.Unit AS U,SUM(T.Quantity) AS X FROM ("+A+") AS T WHERE T.Unit IN (&Units) GROUP BY T.Unit",Params);
        B="SELECT R.Unit AS Unit,R.QuantityClosingBalance AS Quantity FROM AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt,,,Product=&Product AND Warehouse=&Warehouse AND Unit IN (&Units)) AS R";
        V=V+"|"+Report("SELECT T.Unit AS U,SUM(T.Quantity) AS X FROM ("+B+") AS T WHERE T.Unit IN (&Units) GROUP BY T.Unit",Params);
        Return V+"|"+Report("SELECT T.Unit AS U,SUM(T.Quantity) AS X FROM ("+A+" UNION ALL "+B+") AS T GROUP BY T.Unit",Params);
    ElsIf CaseNo=11 Then
        Q=Bound(CatalogRows("P.Unit IN (&Units)"),Params); Params.Units.Add(U2); Old=Q.Execute(); Before=Rows(Old);
        Params.Units.Clear(); Params.Units.Add(UE); After=Rows(Q.Execute()); Detached=Rows(Old);
        Params.Units=New FixedArray(Values(U,UE)); Q.SetParameter("Units",Params.Units);
        Return Before+"|"+After+"|"+Detached+"|"+Rows(Q.Execute());
    ElsIf CaseNo=12 Then
        Before=Report(BalanceRows(),Params); BeginTransaction();
        Try
            Stage="write"; D=Move("rz"+Code,P,W,U,Date(2024,2,7),17);
            Stage="query"; Inside=Report(BalanceRows(),Params); RollbackTransaction();
        Except RollbackTransaction(); Raise; EndTry;
        After=Report(BalanceRows(),Params); Stage="write";
        Target.Lines[0].Quantity=19; Target.Write(DocumentWriteMode.Posting); Stage="query";
        Reposted=Report(BalanceRows(),Params); Stage="write";
        Target.Write(DocumentWriteMode.UndoPosting); Stage="query";
        Return Before+"|"+Inside+"|"+After+"|"+Reposted+"|"+Report(BalanceRows(),Params);
    EndIf;
EndFunction
For CaseNo = 1 To 12 Do
    Stage="setup";
    Try Value=ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())); EndTry;
EndDo;
