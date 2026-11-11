Function N(Val Value)
    If Value = Null Then Return "null"; EndIf;
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Function B(Val Value)
    Return N(Number(Value));
EndFunction
Function Item(Code)
    O = Catalogs.Products.CreateItem(); O.Code = Code; O.Description = "same"; O.Write(); Return O.Ref;
EndFunction
Function Warehouse(Code)
    O = Catalogs.Warehouses.CreateItem(); O.Code = Code; O.Description = "warehouse"; O.Write(); Return O.Ref;
EndFunction
Function DocumentOf(Code, Product, Store, Expense = False)
    If Expense Then O = Documents.Issue.CreateDocument(); Else O = Documents.Receipt.CreateDocument(); EndIf;
    O.Number = Code; O.Date = Date(2024,1,1,12,0,0); O.Warehouse = Store;
    R = O.Lines.Add(); R.Product = Product; R.Quantity = 5; R.Amount = 10;
    Return O;
EndFunction
Function Raw(Tag)
    Q = New Query("SELECT COUNT(*) AS N, SUM(R.Quantity) AS Q FROM AccumulationRegister.Stock AS R WHERE R.Note=&Tag");
    Q.SetParameter("Tag",Tag); S = Q.Execute().Select(); S.Next(); Return N(S.N)+","+N(S.Q);
EndFunction
Function Balance(Product)
    Q = New Query("SELECT P.Code AS P, W.Code AS W, R.QuantityBalance AS Q, R.AmountBalance AS A FROM AccumulationRegister.Stock.Balance(&At) AS R INNER JOIN Catalog.Products AS P ON R.Product=P.Ref INNER JOIN Catalog.Warehouses AS W ON R.Warehouse=W.Ref WHERE R.Product=&Product ORDER BY P,W");
    Q.SetParameter("At",Date(2024,1,2)); Q.SetParameter("Product",Product); S=Q.Execute().Select(); V="";
    While S.Next() Do V=V+S.P+","+S.W+","+N(S.Q)+","+N(S.A)+";"; EndDo;
    If V="" Then Return "empty"; EndIf; Return V;
EndFunction
Function Turnovers(Product)
    Q = New Query("SELECT W.Code AS W, R.QuantityTurnover AS Q, R.QuantityReceipt AS R, R.QuantityExpense AS E FROM AccumulationRegister.Stock.Turnovers(&Start,&EndAt) AS R INNER JOIN Catalog.Warehouses AS W ON R.Warehouse=W.Ref WHERE R.Product=&Product ORDER BY W");
    Q.SetParameter("Start",Date(2024,1,1)); Q.SetParameter("EndAt",Date(2024,1,2)); Q.SetParameter("Product",Product); S=Q.Execute().Select(); V="";
    While S.Next() Do V=V+S.W+","+N(S.Q)+","+N(S.R)+","+N(S.E)+";"; EndDo;
    If V="" Then Return "empty"; EndIf; Return V;
EndFunction
Function ObserveCase(CaseNo, Stage)
    Stage="setup"; Code=String(CaseNo); P=Item("p"+Code); W=Warehouse("w"+Code);
    O=DocumentOf(Code,P,W); Stage="write";
    If CaseNo=1 Then
        D=Documents.Receipt.CreateDocument(); L=D.Lines.Add(); R=D.RegisterRecords.Stock.Add();
        Return B(D.Warehouse=Catalogs.Warehouses.EmptyRef())+","+B(L.Product=Catalogs.Products.EmptyRef())+","+B(R.Product=Catalogs.Products.EmptyRef())+","+B(R.Warehouse=Catalogs.Warehouses.EmptyRef());
    ElsIf CaseNo=2 Then
        Failed="0"; Try O.Warehouse=P; Except Failed="1"; EndTry;
        Header=Failed+","+B(O.Warehouse=W)+","+B(O.Warehouse=Catalogs.Warehouses.EmptyRef());
        Failed="0"; Try O.Lines[0].Product=W; Except Failed="1"; EndTry;
        Line=Failed+","+B(O.Lines[0].Product=P)+","+B(O.Lines[0].Product=Catalogs.Products.EmptyRef());
        R=O.RegisterRecords.Stock.Add(); R.Product=P;
        Failed="0"; Try R.Product=W; Except Failed="1"; EndTry;
        Return Header+"|"+Line+"|"+Failed+","+B(R.Product=P)+","+B(R.Product=Catalogs.Products.EmptyRef());
    ElsIf CaseNo=3 Then
        O.Write(); Stage="readback"; D=O.Ref.GetObject();
        Return B(D.Warehouse=W)+","+B(D.Lines[0].Product=P)+","+N(D.Lines[0].Quantity);
    ElsIf CaseNo=4 Then
        O.Write(DocumentWriteMode.Posting); P2=Item("q"+Code); W2=Warehouse("v"+Code);
        D=DocumentOf("b"+Code,P2,W2); D.Write(DocumentWriteMode.Posting); Stage="query";
        Return Balance(P)+"|"+Balance(P2);
    ElsIf CaseNo=5 Then
        O.Write(DocumentWriteMode.Posting); D=DocumentOf("b"+Code,P,W,True); D.Lines[0].Quantity=2; D.Lines[0].Amount=4; D.Write(DocumentWriteMode.Posting); Stage="query";
        Return Balance(P)+"|"+Turnovers(P);
    ElsIf CaseNo=6 Then
        O.Write(DocumentWriteMode.Posting); Stage="query";
        Q=New Query("SELECT R.Product AS P,R.Warehouse AS W FROM AccumulationRegister.Stock AS R WHERE R.Note=&Tag"); Q.SetParameter("Tag","receipt:"+Code); S=Q.Execute().Select(); S.Next();
        Return B(S.P=P)+","+B(S.W=W)+"|"+Balance(P)+"|"+Turnovers(P);
    ElsIf CaseNo=7 Then
        P2=Item("q"+Code); O.Write(DocumentWriteMode.Posting); D=DocumentOf("b"+Code,P2,W); D.Lines[0].Quantity=2; D.Write(DocumentWriteMode.Posting);
        Before=Balance(P)+"|"+Balance(P2); C=P.GetObject(); C.Description="renamed"; C.Write(); Stage="query";
        Return Before+"|"+Balance(P)+"|"+Balance(P2)+"|"+B(P<>P2);
    ElsIf CaseNo=8 Then
        O.Write(DocumentWriteMode.Posting); P2=Item("q"+Code); W2=Warehouse("v"+Code); D=O.Ref.GetObject(); D.Warehouse=W2; D.Lines[0].Product=P2; D.Write(DocumentWriteMode.Posting); Stage="query";
        Return Balance(P)+"|"+Balance(P2)+"|"+Raw("receipt:"+Code);
    ElsIf CaseNo=9 Then
        O.Write(DocumentWriteMode.Posting); D=O.Ref.GetObject(); D.Lines[0].Quantity=99; D.Write(); Stage="query";
        Return B(O.Ref.GetObject().Posted)+"|"+Raw("receipt:"+Code)+"|"+Balance(P);
    ElsIf CaseNo=10 Then
        O.Write(DocumentWriteMode.Posting); D=DocumentOf("b"+Code,P,W); D.Write(DocumentWriteMode.Posting); O.Write(DocumentWriteMode.UndoPosting); Stage="query";
        Return B(O.Ref.GetObject().Posted)+"|"+Raw("receipt:"+Code)+"|"+Raw("receipt:b"+Code)+"|"+Balance(P);
    ElsIf CaseNo=11 Then
        Result="";
        For Mode=1 To 2 Do
            D=DocumentOf("m"+String(Mode)+Code,P,W); D.AdditionalProperties.Insert("Mode",Mode); Failed="0";
            Try D.Write(DocumentWriteMode.Posting); Except Failed="1"; EndTry;
            Inside=-1; D.AdditionalProperties.Property("Inside",Inside); Stage="query";
            Result=Result+Failed+","+N(Inside)+","+Raw("receipt:m"+String(Mode)+Code)+";";
        EndDo;
        Return Result+"|"+Balance(P);
    ElsIf CaseNo=12 Then
        BeginTransaction();
        Try
            P2=Item("q"+Code); D=DocumentOf("b"+Code,P2,W); D.Write(DocumentWriteMode.Posting); Inside=Balance(P2); RollbackTransaction();
        Except RollbackTransaction(); Raise; EndTry;
        Stage="readback";
        Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Products AS P WHERE P.Ref=&Ref"); Q.SetParameter("Ref",P2); S=Q.Execute().Select(); S.Next();
        Return Inside+"|"+N(S.N)+"|"+Raw("receipt:b"+Code)+"|"+Balance(P2);
    EndIf;
    Raise "unknown owned inventory case";
EndFunction
For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except
        AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
