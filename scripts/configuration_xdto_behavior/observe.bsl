// Owned package observations; results are emitted without expected substitution.
Function ObserveCase(CaseNo, Stage)
    Stage="read";
    F=XDTOFactory;
    T=F.Type("urn:owned:records","Record");
    If CaseNo=1 Then Return String(TypeOf(T))+":"+T.Name+":"+T.NamespaceURI; EndIf;
    If CaseNo=2 Then
        P=F.Packages.Get("urn:owned:records");
        Return P.NamespaceURI+":"+String(P.Count())+":"+String(P.ElementFormQualified)+":"+String(P.AttributeFormQualified);
    EndIf;
    If CaseNo=3 Then Return String(T.Ordered)+":"+String(T.Open)+":"+String(T.Abstract)+":"+String(T.Sequenced)+":"+String(T.Mixed); EndIf;
    If CaseNo=4 Then
        P=T.Properties.Get("Title"); L=T.Properties.Get("Items"); C=T.Properties.Get("Child");
        Return P.Name+":"+P.NamespaceURI+":"+String(P.Qualified)+":"+String(P.Form=XMLForm.Element)+":"+String(P.LowerBound)+":"+String(P.UpperBound)+":"+String(P.Nillable)+":"+String(L.LowerBound)+":"+String(L.UpperBound)+":"+String(C.Nillable);
    EndIf;
    O=F.Create(T);
    If CaseNo=5 Then
        O.Title="я😀"; O.Amount=12.5; O.Validate();
        Return O.Title+":"+Format(O.Amount,"ЧГ=0; ЧРД=.");
    EndIf;
    If CaseNo=6 Then
        Try O.Validate(); Return "validated"; Except Return "error"; EndTry;
    EndIf;
    If CaseNo=7 Then
        A=O.IsSet("Child"); O.Child=Undefined;
        Return String(A)+":"+String(O.IsSet("Child"))+":"+String(O.Child=Undefined);
    EndIf;
    If CaseNo=8 Then
        C=F.Create(F.Type("urn:owned:records","Child")); C.Label="nested"; O.Child=C;
        Return O.Child.Label+":"+String(C.Owner()=O)+":"+C.OwningProperty().Name;
    EndIf;
    If CaseNo=9 Then
        C=F.Create(F.Type("urn:owned:records","Child")); C.Label="one"; O.GetList("Items").Add(C);
        D=F.Create(F.Type("urn:owned:records","Child")); D.Label="two"; O.GetList("Items").Add(D);
        Return String(O.GetList("Items").Count())+":"+O.GetList("Items").Get(0).Label+":"+O.GetList("Items").Get(1).Label;
    EndIf;
    If CaseNo=10 Then
        O.Title="a<&😀"; W=New XMLWriter; W.SetString(); F.WriteXML(W,O,"Record","urn:owned:records"); S=W.Close();
        R=New XMLReader; R.SetString(S); V=F.ReadXML(R,T); R.Close(); Return V.Title;
    EndIf;
    If CaseNo=11 Then
        O.Title="jsonя"; O.Amount=12.5; W=New JSONWriter; W.SetString(); F.WriteJSON(W,O); S=W.Close();
        R=New JSONReader; R.SetString(S); V=F.ReadJSON(R,T); R.Close(); Return V.Title+":"+Format(V.Amount,"ЧГ=0; ЧРД=.");
    EndIf;
    If CaseNo=12 Then
        V=OwnedXDTOBridge.MakeRecord(T);
        Return V.Title+":"+String(V.Type()=T)+":"+String(V.Factory()=F)+":"+String(OwnedXDTOBridge.FactoryMatches(V));
    EndIf;
    Raise "unknown-owned-configuration-xdto-case";
EndFunction

For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); ConfigurationXDTOEmit(CaseNo,Value);
    Except
        ConfigurationXDTODiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
