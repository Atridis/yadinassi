// !todo Advanced DOM
Функция DMEncode(T)
If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "bound";EndIf;
R="S"+S(StrLen(T))+":";
For P=1 To StrLen(T) Do
C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "unit";EndIf;
For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;
R=R+H;
EndDo;Return R;
EndFunction
Функция Z(D,N)
Return D.CreateElement(N);
EndFunction
Функция S(Val V)
Return String(V);
EndFunction
Функция DMRead(T)
X=New XMLReader;X.SetString(T);B=New DOMBuilder;D=B.Read(X);X.Close();Return D;
EndFunction
Функция DMWrite(D)
X=New XMLWriter;X.SetString();W=New DOMWriter;W.Write(D,X);Return X.Close();
EndFunction
Функция DMFile()
Root=GetTempFileName("dom");F=New File(Root);If F.Exists() Then Raise "collision";EndIf;
CreateDirectory(Root);Path=Root+"/a.xml";X=Undefined;Y=Undefined;
Try
D=New DOMDocument("","r");D.DocumentElement.TextContent="я😀";
X=New XMLWriter;X.OpenFile(Path);W=New DOMWriter;W.Write(D,X);X.Close();
Y=New XMLReader;Y.OpenFile(Path);B=New DOMBuilder;E=B.Read(Y);Y.Close();V=E.DocumentElement.TextContent;
DeleteFiles(Path);L=FindFiles(Root,"*");If L.Count()<>0 Then Raise "not-empty";EndIf;DeleteFiles(Root);
Return V+":"+S(Not F.Exists());
Except
Try X.Close();Except EndTry;Try Y.Close();Except EndTry;
Try DeleteFiles(Path);Except EndTry;
Try L=FindFiles(Root,"*");If L.Count()=0 Then DeleteFiles(Root);EndIf;Except EndTry;Raise;
EndTry;
EndFunction
Функция DMCase(N)
D=New DOMDocument("","r");R=D.DocumentElement;
If N=1 Then Return R.NodeName+":"+S(R.OwnerDocument.IsSameNode(D));
ElsIf N=2 Then Return S(R.HasChildNodes())+":"+S(R.HasAttributes())+":"+S(R.NodeValue=Undefined);
ElsIf N=3 Then A=Z(D,"a");X=R.AppendChild(A);Return S(X.IsSameNode(A))+":"+S(A.ParentNode.IsSameNode(R));
ElsIf N=4 Then A=Z(D,"a");B=Z(D,"b");R.AppendChild(A);X=R.InsertBefore(B,A);Return R.FirstChild.NodeName+":"+S(X.IsSameNode(B))+":"+A.PreviousSibling.NodeName;
ElsIf N=5 Then A=Z(D,"a");B=Z(D,"b");R.AppendChild(A);X=R.ReplaceChild(B,A);Return R.FirstChild.NodeName+":"+S(X.IsSameNode(A))+":"+S(A.ParentNode=Undefined);
ElsIf N=6 Then A=Z(D,"a");R.AppendChild(A);X=R.RemoveChild(A);Return S(X.IsSameNode(A))+":"+S(A.ParentNode=Undefined);
ElsIf N=7 Then L=R.ChildNodes;R.AppendChild(Z(D,"a"));R.AppendChild(Z(D,"b"));Return S(L.Count())+":"+L.Item(0).NodeName+":"+L.Item(1).NodeName;
ElsIf N=8 Then R.AppendChild(Z(D,"a"));R.AppendChild(Z(D,"b"));A=R.FirstChild;R.AppendChild(A);Return R.FirstChild.NodeName+":"+R.LastChild.NodeName;
ElsIf N=9 Then A=D.CreateTextNode("я😀x");R.AppendChild(A);Return A.Data+":"+S(A.Length)+":"+R.TextContent;
ElsIf N=10 Then R.AppendChild(Z(D,"a"));R.TextContent="new";Return S(R.ChildNodes.Count())+":"+R.FirstChild.NodeName+":"+R.TextContent;
ElsIf N=11 Then A=D.CreateTextNode("ab");A.AppendData("cd");A.InsertData(1,"X");A.DeleteData(2,1);A.ReplaceData(0,1,"Y");Return A.Data+":"+A.SubstringData(1,2);
ElsIf N=12 Then A=D.CreateTextNode("abcd");R.AppendChild(A);Try B=A.SplitText(2);Except Return "split-error";EndTry;V=A.Data+":"+S(B=Undefined)+":"+S(R.ChildNodes.Count());Try V=V+":"+A.WholeText;Except V=V+":whole-error";EndTry;Return V;
ElsIf N=13 Then R.AppendChild(D.CreateTextNode("a"));R.AppendChild(D.CreateTextNode("b"));R.Normalize();Return S(R.ChildNodes.Count())+":"+R.TextContent;
ElsIf N=14 Then A=D.CreateCDATASection("a<b");R.AppendChild(A);Return A.NodeName+":"+A.Data+":"+R.TextContent;
ElsIf N=15 Then A=D.CreateComment("note");R.AppendChild(A);Return A.NodeName+":"+A.Data+":"+R.TextContent;
ElsIf N=16 Then A=D.CreateProcessingInstruction("task","x=1");R.AppendChild(A);Return A.Target+":"+A.Data+":"+A.NodeName;
ElsIf N=17 Then A=D.CreateDocumentFragment();A.AppendChild(Z(D,"a"));A.AppendChild(D.CreateTextNode("t"));R.AppendChild(A);Return S(A.ChildNodes.Count())+":"+S(R.ChildNodes.Count())+":"+R.TextContent;
ElsIf N=18 Then R.SetAttribute("id","7");Return R.GetAttribute("id")+":"+S(R.HasAttribute("id"))+":"+S(R.Attributes.Count());
ElsIf N=19 Then R.SetAttribute("id","7");R.SetAttribute("id","8");R.RemoveAttribute("id");Return S(R.HasAttribute("id"))+":"+R.GetAttribute("id")+":"+S(R.Attributes.Count());
ElsIf N=20 Then A=D.CreateAttribute("id");A.Value="7";X=R.SetAttributeNode(A);Return S(X=Undefined)+":"+S(A.OwnerElement.IsSameNode(R))+":"+S(A.Specified)+":"+S(A.IsId);
ElsIf N=21 Then R.SetAttribute("id","old");A=D.CreateAttribute("id");A.Value="new";X=R.SetAttributeNode(A);Return X.Value+":"+R.GetAttributeNode("id").Value;
ElsIf N=22 Then R.SetAttribute("id","7");A=R.GetAttributeNode("id");X=R.RemoveAttributeNode(A);Return S(X.IsSameNode(A))+":"+S(A.OwnerElement=Undefined);
ElsIf N=23 Then M=R.Attributes;A=D.CreateAttribute("a");A.Value="v";M.SetNamedItem(A);Return S(M.Count())+":"+M.Item(0).Name+":"+M.GetNamedItem("a").Value;
ElsIf N=24 Then M=R.Attributes;R.SetAttribute("a","v");X=M.RemoveNamedItem("a");Return X.Value+":"+S(M.Count());
ElsIf N=25 Then A=D.CreateElement("urn:n","p:item");R.AppendChild(A);Return A.NamespaceURI+":"+A.Prefix+":"+A.LocalName+":"+A.NodeName;
ElsIf N=26 Then A=D.CreateAttribute("urn:n","p:id");A.Value="v";R.SetAttributeNode(A);Return R.GetAttribute("urn:n","id")+":"+S(R.HasAttribute("urn:n","id"));
ElsIf N=27 Then R.SetNamespaceMapping("p","urn:n");A=Z(D,"a");R.AppendChild(A);Return A.LookupNamespaceURI("p")+":"+A.LookupPrefix("urn:n");
ElsIf N=28 Then A=Z(D,"a");R.AppendChild(A);A.AppendChild(Z(D,"a"));Return S(D.GetElementByTagName("a").Count())+":"+S(R.GetElementByTagName("a").Count());
ElsIf N=29 Then L=D.GetElementByTagName("a");V=S(L.Count());R.AppendChild(Z(D,"a"));V=V+":"+S(L.Count());Try V=V+":"+L.Item(0).NodeName;Except V=V+":item-error";EndTry;Return V;
ElsIf N=30 Then R.AppendChild(D.CreateElement("urn:n","p:a"));R.AppendChild(Z(D,"a"));R.AppendChild(Z(D,"b"));Return S(D.GetElementByTagName("a").Count())+":"+S(D.GetElementByTagName("urn:n","a").Count())+":"+S(D.GetElementByTagName("missing","z").Count());
ElsIf N=31 Then R.SetAttribute("k","v");R.AppendChild(D.CreateTextNode("t"));Try A=R.CloneNode(False);Except Return "clone-error";EndTry;V=S(A=Undefined);Try V=V+":"+A.GetAttribute("k")+":"+S(A.ChildNodes.Count());Except V=V+":read-error";EndTry;Return V;
ElsIf N=32 Then R.AppendChild(D.CreateTextNode("t"));A=R.CloneNode(True);Return S(A.IsEqualNode(R))+":"+S(A.IsSameNode(R));
ElsIf N=33 Then E=New DOMDocument("","other");R.SetAttribute("k","v");R.AppendChild(D.CreateTextNode("t"));A=E.ImportNode(R,True);E.DocumentElement.AppendChild(A);Return A.TextContent+":"+A.GetAttribute("k")+":"+S(A.OwnerDocument.IsSameNode(E));
ElsIf N=34 Then E=New DOMDocument("","other");R.SetAttribute("k","v");R.AppendChild(D.CreateTextNode("t"));A=E.ImportNode(R,False);Return A.GetAttribute("k")+":"+S(A.ChildNodes.Count())+":"+S(A.ParentNode=Undefined);
ElsIf N=35 Then D=DMRead("<r a=""v""><x>я😀</x></r>");Return D.DocumentElement.GetAttribute("a")+":"+D.DocumentElement.FirstChild.TextContent;
ElsIf N=36 Then D=DMRead("<r><![CDATA[a<b]]><!--c--><?task x?></r>");R=D.DocumentElement;V=S(R.ChildNodes.Count())+":"+R.FirstChild.NodeName+":"+R.ChildNodes.Item(1).NodeName+":"+R.LastChild.NodeName;Return V;
ElsIf N=37 Then R.SetAttribute("k","<&"" вы");R.AppendChild(D.CreateTextNode("a<&😀"));E=DMRead(DMWrite(D));Return E.DocumentElement.GetAttribute("k")+":"+E.DocumentElement.TextContent;
ElsIf N=38 Then D=New DOMDocument("urn:n","p:r");D.DocumentElement.AppendChild(D.CreateElement("urn:n","p:a"));E=DMRead(DMWrite(D));Return E.DocumentElement.NamespaceURI+":"+E.DocumentElement.FirstChild.LocalName;
ElsIf N=39 Then R.AppendChild(D.CreateTextNode("sub"));E=DMRead(DMWrite(R));Return E.DocumentElement.NodeName+":"+E.DocumentElement.TextContent;
ElsIf N=40 Then Return DMFile();
EndIf;
EndFunction
Процедура DMObserve(N)
L=Right("0"+S(N),2);
Try V=DMCase(N);Except Сообщить("DM-"+L+": [action-error]");Return;EndTry;
Try R=DMEncode(V);Except Сообщить("DM-"+L+": [observer-error]");Return;EndTry;
Сообщить("DM-"+L+": [ok|"+R+"]");
EndProcedure
Сообщить("DM-C1: ["+DMEncode("")+"]");
Сообщить("DM-C2: ["+DMEncode("A ;""😀")+"]");
For N=1 To 40 Do DMObserve(N);EndDo;
