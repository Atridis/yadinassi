Function Bit(Value)
    If Value Then Return "1"; Else Return "0"; EndIf;
EndFunction
Function Num(Value)
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Function Label(Value, Params)
    If TypeOf(Value)=TypeOf(Null) Then Return "N"; EndIf;
    If TypeOf(Value)=TypeOf(Params.R) Then
        If Value=Params.R Then Return "R"; EndIf;
        If Value=Params.ER Then Return "ER"; EndIf;
        Return "RX";
    EndIf;
    If TypeOf(Value)=TypeOf(Params.I) Then
        If Value=Params.I Then Return "I"; EndIf;
        If Value=Params.EI Then Return "EI"; EndIf;
        Return "IX";
    EndIf;
    If TypeOf(Value)=Type("Number") Then Return Num(Value); EndIf;
    Return "X";
EndFunction
Function ExecuteOwned(Text, Params)
    Q=New Query(Text);
    For Each Pair In Params Do Q.SetParameter(Pair.Key,Pair.Value); EndDo;
    Return Q.Execute();
EndFunction
Function Rows(Text, Params, Ordered=False)
    // Each query is an observation: native refusal is not an expected success.
    Try
        S=ExecuteOwned(Text,Params).Select();
    Except Return "ERR"; EndTry;
    Values=New ValueTable;
        Values.Columns.Add("V"); Count=0;
        While S.Next() Do
            Count=Count+1; If Count>16 Then Raise "owned row bound"; EndIf;
            Row=Values.Add(); Row.V=Label(S[0],Params)+","+Label(S[1],Params);
        EndDo;
        If Not Ordered Then Values.Sort("V"); EndIf;
        Out="OK:"; For Each Row In Values Do Out=Out+Row.V+";"; EndDo;
        Return Out;
EndFunction
Function Types(Text, Params)
    Try
        T=ExecuteOwned(Text,Params).Unload();
    Except Return "ERR"; EndTry;
    If T.Count()>16 Then Raise "owned row bound"; EndIf;
    D=T.Columns[0].ValueType;
        R=False; I=False; N=False; Other=0;
        For Each Kind In D.Types() Do
            If Kind=TypeOf(Params.R) Then R=True;
            ElsIf Kind=TypeOf(Params.I) Then I=True;
            ElsIf Kind=TypeOf(Null) Then N=True;
            Else Other=Other+1; EndIf;
        EndDo;
        Return "OK:"+Num(T.Count())+","+Bit(R)+Bit(I)+Bit(N)+","+Num(Other)+","+Bit(D.ContainsType(TypeOf(Params.R)))+Bit(D.ContainsType(TypeOf(Params.I)))+Bit(D.ContainsType(TypeOf(Null)));
EndFunction
Function NewDocument(Expense, Product, Store, Fixed)
    If Expense Then M=Documents.Issue; Else M=Documents.Receipt; EndIf;
    O=M.CreateDocument();
    If Fixed Then O.SetNewObjectRef(M.GetRef(New UUID("96f037f0-4f02-4421-8c27-98def1836711"))); EndIf;
    If Expense Then O.Number="pr-i"; Else O.Number="pr-r"; EndIf;
    O.Date=Date(2024,1,1,12,0,0); O.Warehouse=Store;
    L=O.Lines.Add(); L.Product=Product; L.Quantity=5; L.Amount=10;
    O.Write(DocumentWriteMode.Posting); Return O.Ref;
EndFunction
Function Setup()
    P=Catalogs.Products.CreateItem(); P.Code="pr-p"; P.Description="owned"; P.Write();
    W=Catalogs.Warehouses.CreateItem(); W.Code="pr-w"; W.Description="owned"; W.Write();
    Params=New Structure; Same="ERR";
    BeginTransaction();
    Try
        R=NewDocument(False,P.Ref,W.Ref,True); I=NewDocument(True,P.Ref,W.Ref,True);
        Same="OK:"+Bit(R.UUID()=I.UUID())+","+Bit(R=I); CommitTransaction();
    Except
        RollbackTransaction();
        // Unsupported document SetNewObjectRef is observed; ordinary setup must
        // still succeed or the packet is incomplete, not eight successful errors.
        R=NewDocument(False,P.Ref,W.Ref,False); I=NewDocument(True,P.Ref,W.Ref,False);
    EndTry;
    Params.Insert("R",R); Params.Insert("I",I); Params.Insert("Same",Same);
    Params.Insert("ER",Documents.Receipt.EmptyRef()); Params.Insert("EI",Documents.Issue.EmptyRef());
    A=New Array; A.Add(R); A.Add(I); Params.Insert("Both",A);
    Params.Insert("Empty",New Array); A=New Array; A.Add(R); A.Add(Null); Params.Insert("WithNull",A);
    Return Params;
EndFunction
Function ObserveCase(CaseNo, P)
    Base="SELECT S.Recorder AS V,1 AS K FROM AccumulationRegister.Stock AS S";
    If CaseNo=1 Then
        Return P.Same+"|"+Rows(Base,P)+"|"+Rows(Base+" WHERE S.Recorder=&R",P)+"|"+Rows(Base+" WHERE S.Recorder=&I",P);
    ElsIf CaseNo=2 Then
        Return Rows(Base+" WHERE S.Recorder=&ER",P)+"|"+Rows(Base+" WHERE S.Recorder=&EI",P)+"|"+Rows(Base+" WHERE S.Recorder<>&R",P)+"|"+Rows(Base+" WHERE &R=&I",P);
    ElsIf CaseNo=3 Then
        Return Rows(Base+" WHERE S.Recorder IN (&Both)",P)+"|"+Rows(Base+" WHERE S.Recorder NOT IN (&Both)",P)+"|"+Rows(Base+" WHERE S.Recorder IN (&Empty)",P)+"|"+Rows(Base+" WHERE S.Recorder NOT IN (&WithNull)",P)+"|"+Rows(Base+" WHERE S.Recorder IN (SELECT D.Ref FROM Document.Receipt AS D)",P);
    ElsIf CaseNo=4 Then
        A="SELECT CASE WHEN S.Recorder=&R THEN &R ELSE &I END AS V,1 AS K FROM AccumulationRegister.Stock AS S";
        B="SELECT CASE WHEN S.Recorder=&R THEN &R END AS V,1 AS K FROM AccumulationRegister.Stock AS S";
        Return Rows(A,P)+"|"+Types(A,P)+"|"+Rows(B,P)+"|"+Types(B,P)+"|"+Rows("SELECT ISNULL(D.Ref,&I) AS V,1 AS K FROM AccumulationRegister.Stock AS S LEFT JOIN Document.Receipt AS D ON S.Recorder=D.Ref",P);
    ElsIf CaseNo=5 Then
        A="SELECT D.Ref AS V,1 AS K FROM Document.Receipt AS D"; B="SELECT D.Ref AS V,1 AS K FROM Document.Issue AS D";
        Return Rows(A+" UNION ALL "+B,P)+"|"+Types(A+" UNION ALL "+B,P)+"|"+Rows(A+" UNION "+B+" UNION "+A,P)+"|"+Types(A+" WHERE FALSE UNION ALL "+B+" WHERE FALSE",P);
    ElsIf CaseNo=6 Then
        Return Types(Base,P)+"|"+Types(Base+" WHERE S.Recorder=&R",P)+"|"+Types(Base+" WHERE FALSE",P)+"|"+Types("SELECT D.Ref AS V,1 AS K FROM AccumulationRegister.Stock AS S LEFT JOIN Document.Receipt AS D ON S.Recorder=D.Ref",P);
    ElsIf CaseNo=7 Then
        Return Rows("SELECT S.Recorder AS V,COUNT(*) AS K FROM AccumulationRegister.Stock AS S GROUP BY S.Recorder",P)+"|"+Rows("SELECT S.Recorder AS V,1 AS K FROM AccumulationRegister.Stock AS S INNER JOIN Document.Receipt AS D ON S.Recorder=D.Ref",P)+"|"+Rows("SELECT S.Recorder AS V,D.Ref AS K FROM AccumulationRegister.Stock AS S LEFT JOIN Document.Receipt AS D ON S.Recorder=D.Ref",P);
    ElsIf CaseNo=8 Then
        Return Rows(Base+" ORDER BY S.Recorder",P,True)+"|"+Rows(Base+" ORDER BY S.Recorder DESC",P,True);
    EndIf;
    Raise "owned case boundary";
EndFunction
P=Setup();
For CaseNo = 1 To 8 Do
    Value=ObserveCase(CaseNo,P); RecorderEmit(CaseNo,Value);
EndDo;
