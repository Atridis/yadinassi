// Ordinary owned in-memory DOM observations; no expected-answer substitution.
Function ReadDocument(Text)
    Reader=New XMLReader; Reader.SetString(Text); Builder=New DOMBuilder;
    Document=Builder.Read(Reader); Reader.Close(); Return Document;
EndFunction

Function CountNodes(Result)
    Count=0;
    While Result.IterateNext()<>Undefined Do
        Count=Count+1;
        If Count>20 Then Raise "owned-result-bound"; EndIf;
    EndDo;
    Return Count;
EndFunction

Function ObserveCase(CaseNo, Stage)
    Stage="read";
    D=ReadDocument("<root><group><item id=""a""/><item id=""b""/></group><group><item id=""c""/></group></root>");
    R=New DOMNamespaceResolver(D);
    If CaseNo=1 Then
        V=D.EvaluateXPathExpression("/root/group/item",D,R); N=V.IterateNext();
        Return String(TypeOf(R))+":"+String(TypeOf(V))+":"+String(V.InvalidIteratorState)+":"+N.GetAttribute("id")+":"+String(CountNodes(V));
    EndIf;
    If CaseNo=2 Then
        D=ReadDocument("<p:root xmlns:p=""urn:owned:p""><p:item/></p:root>"); R=New DOMNamespaceResolver("p","urn:owned:p");
        V=D.EvaluateXPathExpression("/p:root/p:item",D,R); Return String(CountNodes(V));
    EndIf;
    If CaseNo=3 Then
        D=ReadDocument("<root xmlns=""urn:owned:default""><item/></root>"); R=New DOMNamespaceResolver(D);
        Try V=D.EvaluateXPathExpression("/xmlns:root/xmlns:item",D,R); Return "count:"+String(CountNodes(V)); Except Return "error"; EndTry;
    EndIf;
    If CaseNo=4 Then
        D=ReadDocument("<root><group xmlns:p=""urn:owned:p""><p:item/></group></root>");
        N=D.DocumentElement.FirstChild; R=New DOMNamespaceResolver(N); V=D.EvaluateXPathExpression("p:item",N,R);
        Return String(CountNodes(V));
    EndIf;
    If CaseNo=5 Then
        V=D.EvaluateXPathExpression("//item[1]",D,R); A=V.IterateNext(); B=V.IterateNext();
        Return A.GetAttribute("id")+":"+B.GetAttribute("id")+":"+String(V.IterateNext()=Undefined);
    EndIf;
    If CaseNo=6 Then
        D=ReadDocument("<root xmlns:p=""urn:owned:p"" id=""a""/>"); R=New DOMNamespaceResolver(D);
        V=D.EvaluateXPathExpression("/root/@*",D,R); Return String(CountNodes(V));
    EndIf;
    If CaseNo=7 Then
        V=D.EvaluateXPathExpression("//item[@id='b']",D,R); N=V.IterateNext();
        Return N.GetAttribute("id")+":"+String(N.IsSameNode(D.DocumentElement.FirstChild.LastChild));
    EndIf;
    If CaseNo=8 Then
        V=D.EvaluateXPathExpression("//item",D,R); N=D.CreateElement("extra"); D.DocumentElement.AppendChild(N);
        Flag=V.InvalidIteratorState; Try N=V.IterateNext(); Status="ok"; Except Status="error"; EndTry;
        Return String(Flag)+":"+Status;
    EndIf;
    If CaseNo=9 Then
        V=D.EvaluateXPathExpression("//item",D,R); N=D.CreateElement("detached");
        Return String(V.InvalidIteratorState)+":"+String(CountNodes(V));
    EndIf;
    If CaseNo=10 Then
        V=D.EvaluateXPathExpression("//item",D,R); D.DocumentElement.SetAttribute("a","b"); A=V.InvalidIteratorState;
        V=D.EvaluateXPathExpression("//item",D,R); D.DocumentElement.FirstChild.FirstChild.TextContent="changed"; B=V.InvalidIteratorState;
        Return String(A)+":"+String(B);
    EndIf;
    If CaseNo=11 Then
        V=D.EvaluateXPathExpression("//item",D,R); D.DocumentElement.SetNamespaceMapping("p","urn:owned:p");
        Return String(V.InvalidIteratorState);
    EndIf;
    If CaseNo=12 Then
        Try V=D.EvaluateXPathExpression("//missing:item",D,R); A="accepted"; Except A="error"; EndTry;
        Other=ReadDocument("<other/>");
        Try V=D.EvaluateXPathExpression(".",Other,R); B="accepted"; Except B="error"; EndTry;
        Return A+":"+B;
    EndIf;
    Raise "unknown-owned-dom-xpath-case";
EndFunction

For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); DOMXPathEmit(CaseNo,Value);
    Except
        DOMXPathDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
