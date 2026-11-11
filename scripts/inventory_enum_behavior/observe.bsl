// Independent source-owned persistence observations. No expected answers.
// The controller executes cases 1..11, waits for full Enterprise exit, then
// executes case 12 in a second Enterprise process against the same infobase.
Function N(Val Value)
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Function B(Val Value)
    If Value Then Return "true"; EndIf; Return "false";
EndFunction
Function E(Val Value)
    If TypeOf(Value)=Type("EnumRef.Units") Then Return "u"+N(Enums.Units.IndexOf(Value)); EndIf;
    If TypeOf(Value)=Type("EnumRef.States") Then Return "s"+N(Enums.States.IndexOf(Value)); EndIf;
    If Value=Undefined Then Return "undefined"; EndIf;
    Return "other";
EndFunction
Function Product(Val Code,Val Unit)
    O=Catalogs.Products.CreateItem(); O.Code=Code; O.Description=Code; O.Unit=Unit; O.Write(); Return O.Ref;
EndFunction
Function Warehouse()
    W=Catalogs.Warehouses.FindByCode("EN-W");
    If W.IsEmpty() Then O=Catalogs.Warehouses.CreateItem(); O.Code="EN-W"; O.Description="Owned"; O.Write(); W=O.Ref; EndIf;
    Return W;
EndFunction
Function Document(Val Number,Val Unit,Val State,Val Qty)
    O=Documents.Receipt.CreateDocument(); O.Number=Number; O.Date=Date(2024,2,10);
    O.Warehouse=Warehouse(); O.State=State;
    L=O.Lines.Add(); L.Product=Catalogs.Products.FindByCode("EN-P"); L.Unit=Unit; L.Quantity=Qty; L.Amount=Qty*2;
    Return O;
EndFunction
Function Bound(Val Text,Val Unit=Undefined)
    Q=New Query(Text);
    Q.SetParameter("StartAt",Date(2024,1,1)); Q.SetParameter("EndAt",Date(2024,3,31,23,59,59));
    If Unit<>Undefined Then Q.SetParameter("Unit",Unit); EndIf;
    Q.SetParameter("Product",Catalogs.Products.FindByCode("EN-P"));
    Q.SetParameter("State",Enums.States.Approved); Return Q;
EndFunction
Function Scalar(Val Text,Val Unit=Undefined)
    S=Bound(Text,Unit).Execute().Select(); If Not S.Next() Then Return "empty"; EndIf;
    Return N(S.N);
EndFunction
Function EnumRows(Val Text,Val Unit=Undefined)
    S=Bound(Text,Unit).Execute().Select(); Result="";
    While S.Next() Do Result=Result+E(S.V)+","+N(S.N)+";"; EndDo;
    If Result="" Then Return "empty"; EndIf;
    Return Result;
EndFunction
Function Assignment(Val Slot,Val Value)
    O=Document("unused",Enums.Units.Piece,Enums.States.Draft,1);
    C=Catalogs.Products.CreateItem(); R=O.RegisterRecords.Stock.Add();
    Try
        If Slot=1 Then C.Unit=Value; Result=C.Unit;
        ElsIf Slot=2 Then O.State=Value; Result=O.State;
        ElsIf Slot=3 Then O.Lines[0].Unit=Value; Result=O.Lines[0].Unit;
        ElsIf Slot=4 Then R.Unit=Value; Result=R.Unit;
        Else R.State=Value; Result=R.State;
        EndIf;
        Return "accepted:"+E(Result);
    Except Return "refused";
    EndTry;
EndFunction
Function ObserveCase(Val CaseNo, Stage)
    Stage="read";
    If CaseNo=1 Then
        C=Catalogs.Products.CreateItem(); D=Documents.Receipt.CreateDocument(); L=D.Lines.Add(); R=D.RegisterRecords.Stock.Add();
        Return E(C.Unit)+","+E(D.State)+","+E(L.Unit)+","+E(R.Unit)+","+E(R.State)+"|"+
            B(Metadata.Catalogs.Products.Attributes.Unit.Type.ContainsType(Type("EnumRef.Units")))+","+
            B(Metadata.Documents.Receipt.Attributes.State.Type.ContainsType(Type("EnumRef.States")));
    ElsIf CaseNo=2 Then
        Stage="write"; P=Product("EN-P",Enums.Units.Piece); Other=Product("EN-PACK",Enums.Units.Pack);
        Stage="readback"; O=P.GetObject();
        Return E(O.Unit)+","+B(O.Unit=Enums.Units.Piece)+","+B(TypeOf(O.Unit)=Type("EnumRef.Units"));
    ElsIf CaseNo=3 Then
        Stage="write"; O=Document("EN-D3",Enums.Units.Pack,Enums.States.Approved,2); O.Write();
        Stage="readback"; D=O.Ref.GetObject();
        Return E(D.State)+","+E(D.Lines[0].Unit)+","+N(D.Lines.Count());
    ElsIf CaseNo=4 Then
        Result="";
        For Slot=1 To 5 Do
            If Slot=2 Or Slot=5 Then Wrong=Enums.Units.Piece; Else Wrong=Enums.States.Draft; EndIf;
            Result=Result+Assignment(Slot,Wrong)+","+Assignment(Slot,"Piece")+","+Assignment(Slot,1)+","+Assignment(Slot,Undefined)+";";
        EndDo;
        Stage="query";
        Try Value=Scalar("SELECT COUNT(*) AS N FROM Catalog.Products WHERE Unit=&Unit",Enums.States.Draft); Result=Result+"query:"+Value;
        Except Result=Result+"query-refused";
        EndTry;
        Return Result;
    ElsIf CaseNo=5 Then
        Stage="write"; P=Product("EN-EMPTY",Enums.Units.EmptyRef());
        O=Document("EN-D5",Enums.Units.EmptyRef(),Enums.States.EmptyRef(),1); O.Write(DocumentWriteMode.Posting);
        Stage="readback"; D=O.Ref.GetObject();
        Return E(P.GetObject().Unit)+","+E(D.State)+","+E(D.Lines[0].Unit)+"|"+
            EnumRows("SELECT R.Unit AS V,R.Quantity AS N FROM AccumulationRegister.Stock AS R WHERE R.Unit=&Unit",Enums.Units.EmptyRef());
    ElsIf CaseNo=6 Then
        Stage="write"; O=Document("EN-D6",Enums.Units.Piece,Enums.States.Approved,2);
        L=O.Lines.Add(); L.Product=Catalogs.Products.FindByCode("EN-P"); L.Unit=Enums.Units.Piece; L.Quantity=3; L.Amount=6;
        L=O.Lines.Add(); L.Product=Catalogs.Products.FindByCode("EN-P"); L.Unit=Enums.Units.Pack; L.Quantity=4; L.Amount=8;
        O.Write(DocumentWriteMode.Posting);
        Stage="query";
        Return Scalar("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock WHERE Unit=&Unit",Enums.Units.Piece)+"|"+
            Scalar("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock WHERE State=&State");
    ElsIf CaseNo=7 Then
        Stage="query";
        Return EnumRows("SELECT P.Unit AS V,1 AS N FROM Catalog.Products AS P WHERE P.Unit=&Unit",Enums.Units.Pack)+"|"+
            EnumRows("SELECT D.State AS V,1 AS N FROM Document.Receipt AS D WHERE D.State=&State")+"|"+
            EnumRows("SELECT L.Unit AS V,L.Quantity AS N FROM Document.Receipt.Lines AS L WHERE L.Unit=&Unit",Enums.Units.Pack)+"|"+
            Scalar("SELECT COUNT(*) AS N FROM Catalog.Products WHERE Unit<>&Unit",Enums.Units.EmptyRef());
    ElsIf CaseNo=8 Then
        Stage="query";
        Text="SELECT COUNT(*) AS N FROM Catalog.Products AS P INNER JOIN AccumulationRegister.Stock AS R ON P.Unit=R.Unit WHERE P.Unit=&Unit";
        First=Scalar(Text,Enums.Units.Piece);
        Text="SELECT COUNT(*) AS N FROM Catalog.Products AS P LEFT JOIN Document.Receipt.Lines AS L ON P.Unit=L.Unit WHERE L.Unit IS NULL";
        Return First+"|"+Scalar(Text);
    ElsIf CaseNo=9 Then
        Stage="query";
        // Scalar result ordering is explicit; EnumRef ordering is not inferred.
        Return EnumRows("SELECT R.Unit AS V,SUM(R.Quantity) AS N FROM AccumulationRegister.Stock AS R GROUP BY R.Unit ORDER BY N")+"|"+
            Scalar("SELECT COUNT(DISTINCT R.Unit) AS N FROM AccumulationRegister.Stock AS R");
    ElsIf CaseNo=10 Then
        Stage="query";
        Return EnumRows("SELECT R.Unit AS V,R.QuantityBalance AS N FROM AccumulationRegister.Stock.Balance(&EndAt) AS R WHERE R.Unit=&Unit",Enums.Units.Piece)+"|"+
            EnumRows("SELECT R.Unit AS V,R.QuantityTurnover AS N FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt) AS R WHERE R.Unit=&Unit",Enums.Units.Pack)+"|"+
            EnumRows("SELECT R.Unit AS V,R.QuantityClosingBalance AS N FROM AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt,Month) AS R WHERE R.Unit=&Unit ORDER BY R.Period",Enums.Units.Piece);
    ElsIf CaseNo=11 Then
        Stage="write"; BeginTransaction();
        Try
            D=Document("EN-D11",Enums.Units.Piece,Enums.States.Draft,7); D.Write(DocumentWriteMode.Posting);
            Inside=Scalar("SELECT SUM(QuantityBalance) AS N FROM AccumulationRegister.Stock.Balance(&EndAt) WHERE Unit=&Unit",Enums.Units.Piece);
            RollbackTransaction();
        Except
            If TransactionActive() Then RollbackTransaction(); EndIf; Raise;
        EndTry;
        After=Scalar("SELECT SUM(QuantityBalance) AS N FROM AccumulationRegister.Stock.Balance(&EndAt) WHERE Unit=&Unit",Enums.Units.Piece);
        D=Document("EN-D11",Enums.Units.Piece,Enums.States.Draft,7); D.Write(DocumentWriteMode.Posting);
        D.Lines[0].Unit=Enums.Units.Pack; D.Write(DocumentWriteMode.Posting);
        Reposted=Scalar("SELECT SUM(QuantityBalance) AS N FROM AccumulationRegister.Stock.Balance(&EndAt) WHERE Unit=&Unit",Enums.Units.Piece);
        D.Write(DocumentWriteMode.UndoPosting);
        Removed=Scalar("SELECT SUM(QuantityBalance) AS N FROM AccumulationRegister.Stock.Balance(&EndAt) WHERE Unit=&Unit",Enums.Units.Pack);
        Return Inside+"|"+After+"|"+Reposted+"|"+Removed;
    ElsIf CaseNo=12 Then
        // This case must run only after the first Enterprise process exited.
        P=Catalogs.Products.FindByCode("EN-P").GetObject(); Empty=Catalogs.Products.FindByCode("EN-EMPTY").GetObject();
        D=Documents.Receipt.FindByNumber("EN-D3").GetObject();
        Return E(P.Unit)+","+E(Empty.Unit)+","+E(D.State)+","+E(D.Lines[0].Unit)+"|"+
            B(P.Unit=Enums.Units.Piece)+","+B(Empty.Unit=Enums.Units.EmptyRef())+","+
            B(D.State=Enums.States.Approved)+"|"+
            Scalar("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock WHERE Unit=&Unit",Enums.Units.Piece);
    EndIf;
    Raise "unknown owned enum persistence case";
EndFunction
For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); AccumulationEmit(CaseNo,Value);
    Except
        AccumulationDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
