// !todo Imports, DTD, recursive/mixed/choice/inheritance schemas deferred.
Функция XFEncode(T)
If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "bound";EndIf;
R="S"+String(StrLen(T))+":";
For P=1 To StrLen(T) Do
C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "unit";EndIf;
For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;
R=R+H;
EndDo;Return R;
EndFunction
Функция XFSetup()
Root=GetTempFileName("xdto");E=New File(Root);If E.Exists() Then Raise "collision";EndIf;
CreateDirectory(Root);Path=Root+"/a.xsd";W=Undefined;
Try
W=New TextWriter(Path,"UTF-8");W.Write("<xs:schema xmlns:xs=""http://www.w3.org/2001/XMLSchema"" xmlns:t=""urn:packet"" targetNamespace=""urn:packet"" elementFormDefault=""qualified""><xs:complexType name=""Child""><xs:sequence><xs:element name=""code"" type=""xs:string""/></xs:sequence></xs:complexType><xs:complexType name=""Box""><xs:sequence><xs:element name=""title"" type=""xs:string"" minOccurs=""0""/><xs:element name=""qty"" type=""xs:decimal"" minOccurs=""0""/><xs:element name=""flag"" type=""xs:boolean"" minOccurs=""0""/><xs:element name=""item"" type=""t:Child"" minOccurs=""0"" maxOccurs=""unbounded""/><xs:element name=""tag"" type=""xs:string"" minOccurs=""0"" maxOccurs=""unbounded""/></xs:sequence><xs:attribute name=""id"" type=""xs:string""/></xs:complexType><xs:element name=""box"" type=""t:Box""/></xs:schema>");W.Close();F=CreateXDTOFactory(Path);
DeleteFiles(Path);L=FindFiles(Root,"*");If L.Count()<>0 Then Raise "not-empty";EndIf;DeleteFiles(Root);
If E.Exists() Then Raise "cleanup";EndIf;Return F;
Except
Try W.Close();Except EndTry;Try DeleteFiles(Path);Except EndTry;
Try L=FindFiles(Root,"*");If L.Count()=0 Then DeleteFiles(Root);EndIf;Except EndTry;Raise;
EndTry;
EndFunction
Функция XFValue(F,T,V)
Return F.Create(F.Type("http://www.w3.org/2001/XMLSchema",T),V);
EndFunction
Функция XFXML(F,O,T)
W=New XMLWriter;W.SetString();F.WriteXML(W,O,"box","urn:packet");S=W.Close();R=New XMLReader;R.SetString(S);V=F.ReadXML(R,T);R.Close();Return V;
EndFunction
Функция XFJSON(F,O,T)
W=New JSONWriter;W.SetString();F.WriteJSON(W,O);S=W.Close();R=New JSONReader;R.SetString(S);V=F.ReadJSON(R,T);R.Close();Return V;
EndFunction
Функция XFCase(N,F)
T=F.Type("urn:packet","Box");O=F.Create(T);
If N=1 Then Return T.Name+":"+T.NamespaceURI;
ElsIf N=2 Then P=F.Packages.Get("urn:packet");Return String(P.Count())+":"+P.Get("Box").Name;
ElsIf N=3 Then P=F.Packages.Get("urn:packet");Return String(P.ElementFormQualified)+":"+String(P.AttributeFormQualified)+":"+P.RootProperties.Get("box").Type.Name;
ElsIf N=4 Then Return String(T.Ordered)+":"+String(T.Sequenced)+":"+String(T.Open)+":"+String(T.Mixed)+":"+String(T.Abstract);
ElsIf N=5 Then Return String(T.Properties.Count())+":"+T.Properties.Get(0).Name+":"+O.Properties().Get("title").Type.Name;
ElsIf N=6 Then P=T.Properties.Get("tag");Return String(P.LowerBound)+":"+String(P.UpperBound)+":"+String(P.Nillable);
ElsIf N=7 Then P=T.Properties.Get("id");Return P.LocalName+":"+String(P.Form=XMLForm.Attribute)+":"+String(P.Qualified);
ElsIf N=8 Then P=T.Properties.Get("title");Return String(P.OwnerType=T)+":"+String(P.Form=XMLForm.Element)+":"+String(P.Qualified);
ElsIf N=9 Then V=XFValue(F,"string","я😀");Return V.Value+":"+V.LexicalValue+":"+V.Type().Name;
ElsIf N=10 Then V=XFValue(F,"boolean","true");Return String(V.Value)+":"+V.LexicalValue;
ElsIf N=11 Then V=XFValue(F,"boolean",False);Return String(V.Value)+":"+V.LexicalValue;
ElsIf N=12 Then V=XFValue(F,"decimal","12.50");Return Format(V.Value,"ЧГ=0; ЧРД=.")+":"+V.LexicalValue;
ElsIf N=13 Then V=XFValue(F,"int","-7");Return String(V.Value)+":"+V.LexicalValue;
ElsIf N=14 Then V=XFValue(F,"date","2024-02-29");Return Format(V.Value,"ДФ=yyyyMMdd")+":"+V.LexicalValue;
ElsIf N=15 Then V=XFValue(F,"dateTime","2024-02-29T12:34:56");Return Format(V.Value,"ДФ=yyyyMMddHHmmss");
ElsIf N=16 Then V=XFValue(F,"string","");Return String(V.Value="")+":"+String(V.Factory()=F);
ElsIf N=17 Then O.title="hello";Return O.title+":"+O.Get("title")+":"+O.GetXDTO("title").Type().Name;
ElsIf N=18 Then O.Set(T.Properties.Get("title"),XFValue(F,"string","v"));Return O.Get("title")+":"+String(O.IsSet("title"));
ElsIf N=19 Then A=O.IsSet("title");O.title="";B=O.IsSet("title");O.Unset("title");Return String(A)+":"+String(B)+":"+String(O.IsSet("title"));
ElsIf N=20 Then O.qty=12;O.flag=True;O.id="K";Return String(O.qty)+":"+String(O.flag)+":"+O.id;
ElsIf N=21 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));Return String(L.Count())+":"+L.Get(0)+":"+L.GetXDTO(0).LexicalValue;
ElsIf N=22 Then L=O.GetList("tag");L.Add(XFValue(F,"string","b"));V=L.Insert(0,XFValue(F,"string","a"));Return L.Get(0)+":"+L.Get(1)+":"+V.LexicalValue;
ElsIf N=23 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));V=L.Set(0,XFValue(F,"string","b"));Return L.Get(0)+":"+V.LexicalValue;
ElsIf N=24 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));V=L.Delete(0);Return String(L.Count())+":"+V.LexicalValue;
ElsIf N=25 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));L.Clear();Return String(L.Count())+":"+String(O.IsSet("tag"));
ElsIf N=26 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));O.Unset("tag");Return String(L.Count())+":"+String(O.GetList("tag").Count());
ElsIf N=27 Then C=F.Create(F.Type("urn:packet","Child"));C.code="c";O.GetList("item").Add(C);Return String(C.Owner()=O)+":"+C.OwningProperty().Name+":"+O.GetList("item").Get(0).code;
ElsIf N=28 Then Return String(O.Type()=T)+":"+String(O.Factory()=F)+":"+String(O.Owner()=Undefined);
ElsIf N=29 Then O.title="a<&😀";O.id="v";A=XFXML(F,O,T);Return A.title+":"+A.id;
ElsIf N=30 Then O.qty=12.5;O.flag=True;A=XFXML(F,O,T);Return Format(A.qty,"ЧГ=0; ЧРД=.")+":"+String(A.flag);
ElsIf N=31 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));L.Add(XFValue(F,"string","b"));A=XFXML(F,O,T);Return String(A.GetList("tag").Count())+":"+A.GetList("tag").Get(1);
ElsIf N=32 Then C=F.Create(F.Type("urn:packet","Child"));C.code="c";O.GetList("item").Add(C);A=XFXML(F,O,T);Return A.GetList("item").Get(0).code;
ElsIf N=33 Then O.title="я😀";A=XFJSON(F,O,T);Return A.title+":"+A.Type().Name;
ElsIf N=34 Then O.qty=12.5;O.flag=False;O.id="v";A=XFJSON(F,O,T);Return Format(A.qty,"ЧГ=0; ЧРД=.")+":"+String(A.flag)+":"+A.id;
ElsIf N=35 Then L=O.GetList("tag");L.Add(XFValue(F,"string","a"));L.Add(XFValue(F,"string","b"));A=XFJSON(F,O,T);Return String(A.GetList("tag").Count())+":"+A.GetList("tag").Get(1);
ElsIf N=36 Then C=F.Create(F.Type("urn:packet","Child"));C.code="c";O.GetList("item").Add(C);A=XFJSON(F,O,T);Return A.GetList("item").Get(0).code;
ElsIf N=37 Then A=XFXML(F,O,T);Return String(A.IsSet("title"))+":"+String(A.GetList("tag").Count());
ElsIf N=38 Then O.title="";A=XFJSON(F,O,T);Return String(A.IsSet("title"))+":"+String(A.title="");
ElsIf N=39 Then O.title="ok";O.Validate();Return O.title+":"+String(TypeOf(O)=Type("XDTODataObject"));
ElsIf N=40 Then V=XFValue(F,"string","ok");V.Type().Validate("ok");Return String(TypeOf(V)=Type("XDTODataValue"))+":"+String(TypeOf(F)=Type("XDTOFactory"));
EndIf;
EndFunction
Процедура XFObserve(N,F)
L=Right("0"+String(N),2);
Try V=XFCase(N,F);Except Сообщить("XF-"+L+": [action-error]");Return;EndTry;
Try R=XFEncode(V);Except Сообщить("XF-"+L+": [observer-error]");Return;EndTry;
Сообщить("XF-"+L+": [ok|"+R+"]");
EndProcedure
Сообщить("XF-C1: ["+XFEncode("")+"]");
Сообщить("XF-C2: ["+XFEncode("A ;""😀")+"]");
Try F=XFSetup();Except F=Undefined;EndTry;
For N=1 To 40 Do XFObserve(N,F);EndDo;
