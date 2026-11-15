// Raw observations from supplied linked packages, not expected substitutions.
Function ObserveCase(CaseNo, Stage)
    Stage="read";
    F=XDTOFactory; A=F.Type("urn:owned:records","Code"); B=F.Type("http://www.w3.org/2001/XMLSchema","string");
    T=F.Type("urn:owned:envelope","Envelope");
    If CaseNo=1 Then Return String(TypeOf(A))+":"+A.Name+":"+A.NamespaceURI+":"+A.BaseType.Name; EndIf;
    If CaseNo=2 Then Return String(A.IsDescendant(A))+":"+String(A.IsDescendant(B))+":"+String(B.IsDescendant(A))+":"+String(A.IsDescendant(F.Type("http://www.w3.org/2001/XMLSchema","decimal"))); EndIf;
    If CaseNo=3 Then V=F.Create(A,"я😀"); Return V.Value+":"+V.LexicalValue+":"+String(V.Type()=A); EndIf;
    If CaseNo=4 Then V=F.Create(F.Type("urn:owned:records","AmountValue"),12.5); Return Format(V.Value,"ЧГ=0; ЧРД=.")+":"+V.LexicalValue+":"+V.Type().Name; EndIf;
    O=F.Create(T); O.Code="owned";
    If CaseNo=5 Then Return O.Code+":"+O.GetXDTO("Code").Type().Name+":"+String(O.GetXDTO("Code").Type()=A); EndIf;
    If CaseNo=6 Then
        Try O.BaseText=F.Create(A,"alias"); Return O.BaseText+":"+O.GetXDTO("BaseText").Type().Name+":"+O.GetXDTO("BaseText").Type().NamespaceURI; Except Return "error"; EndTry;
    EndIf;
    If CaseNo=7 Then
        Try O.Code=F.Create(B,"base"); Return O.Code+":"+O.GetXDTO("Code").Type().Name+":"+O.GetXDTO("Code").Type().NamespaceURI; Except Return "error"; EndTry;
    EndIf;
    If CaseNo=8 Then C=F.Create(F.Type("urn:owned:records","Child")); C.Label="nested"; O.Child=C; Return O.Child.Label+":"+String(O.Child.Type()=F.Type("urn:owned:records","Child"))+":"+C.OwningProperty().NamespaceURI; EndIf;
    If CaseNo=9 Then
        O.Code="a<&😀"; W=New XMLWriter; W.SetString(); F.WriteXML(W,O,"Envelope","urn:owned:envelope"); S=W.Close(); R=New XMLReader; R.SetString(S); V=F.ReadXML(R,T); R.Close(); Return V.Code+":"+String(V.GetXDTO("Code").Type()=A);
    EndIf;
    If CaseNo=10 Then
        O.Code="jsonя"; W=New JSONWriter; W.SetString(); F.WriteJSON(W,O); S=W.Close(); R=New JSONReader; R.SetString(S); V=F.ReadJSON(R,T); R.Close(); Return V.Code+":"+String(V.GetXDTO("Code").Type()=A);
    EndIf;
    If CaseNo=11 Then
        Try V=F.Create(F.Type("urn:owned:records","AmountValue"),"not-a-number"); Return "accepted:"+V.LexicalValue; Except Return "error"; EndTry;
    EndIf;
    If CaseNo=12 Then V=OwnedXDTOBridge.MakeRecord(T); Return V.Code+":"+String(V.Type()=T)+":"+String(V.GetXDTO("Code").Type()=A)+":"+String(OwnedXDTOBridge.FactoryMatches(V)); EndIf;
    Raise "unknown-owned-linked-xdto-case";
EndFunction

For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); ConfigurationXDTOLinkedEmit(CaseNo,Value);
    Except
        ConfigurationXDTOLinkedDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
