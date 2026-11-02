// !todo Async/TLS/auth/proxy/external hosts deferred. Server-only owned loopback.
Функция HTEncode(T)
If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "bound";EndIf;
R="S"+String(StrLen(T))+":";
For P=1 To StrLen(T) Do
C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "unit";EndIf;
For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;
R=R+H;
EndDo;Return R;
EndFunction
Функция HTFile(N,C,Root)
I=Root+"/http-in.bin";O=Root+"/http-out.bin";A=New File(I);B=New File(O);
If A.Exists() Or B.Exists() Then Raise "collision";EndIf;
Try
D=GetBinaryDataFromString("abc");D.Write(I);Q=New HTTPRequest("/echo");Q.SetBodyFileName(I);
If N=37 Then V=String(Q.GetBodyFileName()=I)+":"+String(Q.GetBodyAsString()=Undefined)+":"+String(Q.GetBodyAsBinaryData()=Undefined);
ElsIf N=38 Then R=C.Post(Q);V=R.GetBodyAsString()+":"+String(A.Exists());
ElsIf N=39 Then R=C.Get(New HTTPRequest("/binary"),O);D=New BinaryData(O);V=Base64String(D)+":"+String(R.GetBodyAsBinaryData()=Undefined)+":"+String(R.GetBodyFileName()=O);
Else R=C.Post(Q,O);D=New BinaryData(O);V=Base64String(D)+":"+String(R.GetBodyAsString()=Undefined)+":"+String(R.GetBodyFileName()=O);
EndIf;
Q=Undefined;R=Undefined;D=Undefined;
DeleteFiles(I);If B.Exists() Then DeleteFiles(O);EndIf;
If A.Exists() Or B.Exists() Then Raise "cleanup";EndIf;Return V;
Except
Q=Undefined;R=Undefined;D=Undefined;
Try DeleteFiles(I);Except EndTry;Try DeleteFiles(O);Except EndTry;Raise;
EndTry;
EndFunction
Функция HTCase(N,C,Root)
Q=New HTTPRequest("/echo");
If N=1 Then Return String(C.Host="127.0.0.1")+":"+String(C.Timeout)+":"+String(C.UseOSAuthentication);
ElsIf N=2 Then Q=New HTTPRequest;Return Q.ResourceAddress+":"+String(Q.Headers.Count());
ElsIf N=3 Then H=New Map;H.Insert("X-Probe","one");Q=New HTTPRequest("/headers",H);H.Insert("X-Probe","two");Return Q.Headers.Get("X-Probe");
ElsIf N=4 Then Q.ResourceAddress="/text";Return Q.ResourceAddress;
ElsIf N=5 Then Return String(Q.GetBodyAsBinaryData()=Undefined);
ElsIf N=6 Then Return String(Q.GetBodyAsString()=Undefined);
ElsIf N=7 Then Return String(Q.GetBodyFileName()=Undefined);
ElsIf N=8 Then Q.SetBodyFromString("я😀");Return Q.GetBodyAsString()+":"+Base64String(Q.GetBodyAsBinaryData());
ElsIf N=9 Then Q.SetBodyFromString("a","UTF-8",ByteOrderMarkUse.DontUse);Return Base64String(Q.GetBodyAsBinaryData());
ElsIf N=10 Then Q.SetBodyFromString("a","UTF-8",ByteOrderMarkUse.Use);Return Base64String(Q.GetBodyAsBinaryData());
ElsIf N=11 Then Q.SetBodyFromString("a","UTF-16LE",ByteOrderMarkUse.Auto);Return Base64String(Q.GetBodyAsBinaryData());
ElsIf N=12 Then Q.SetBodyFromString("a","UTF-16BE",ByteOrderMarkUse.Use);Return Base64String(Q.GetBodyAsBinaryData());
ElsIf N=13 Then Q.SetBodyFromString("Привет","windows-1251",ByteOrderMarkUse.DontUse);Return Q.GetBodyAsString()+":"+Base64String(Q.GetBodyAsBinaryData());
ElsIf N=14 Then Q.SetBodyFromString("");Return String(Q.GetBodyAsString()="")+":"+String(Q.GetBodyAsBinaryData().Size());
ElsIf N=15 Then Q.SetBodyFromBinaryData(Base64Value("AP9B"));Return Base64String(Q.GetBodyAsBinaryData());
ElsIf N=16 Then Q.SetBodyFromString("old");Q.SetBodyFromBinaryData(GetBinaryDataFromString("new"));Return Q.GetBodyAsString();
ElsIf N=17 Then Q.Headers.Insert("X-Probe","owned");Return Q.Headers.Get("X-Probe")+":"+String(Q.Headers.Count());
ElsIf N=18 Then S=Q.GetBodyAsStream();B=New BinaryDataBuffer(1);B.Set(0,65);S.Write(B,0,1);V=String(S.CanWrite)+":"+String(S.CurrentPosition());S.Close();Return V+":"+Base64String(Q.GetBodyAsBinaryData());
ElsIf N=19 Then R=C.Get(New HTTPRequest("/text"));Return String(R.StatusCode)+":"+String(TypeOf(R)=Type("HTTPResponse"));
ElsIf N=20 Then R=C.Get(New HTTPRequest("/text"));Return R.GetBodyAsString();
ElsIf N=21 Then R=C.Get(New HTTPRequest("/binary"));Return Base64String(R.GetBodyAsBinaryData());
ElsIf N=22 Then R=C.Get(New HTTPRequest("/latin"));Return R.GetBodyAsString();
ElsIf N=23 Then R=C.Get(New HTTPRequest("/latin"));Return R.GetBodyAsString("windows-1251");
ElsIf N=24 Then R=C.Get(New HTTPRequest("/empty"));Return String(R.StatusCode)+":"+String(R.GetBodyAsBinaryData().Size())+":"+String(R.GetBodyAsString()="");
ElsIf N=25 Then R=C.Get(New HTTPRequest("/missing"));Return String(R.StatusCode)+":"+R.GetBodyAsString();
ElsIf N=26 Then R=C.Get(New HTTPRequest("/headers"));Return R.Headers.Get("X-Fixture")+":"+R.Headers.Get("X-Dup");
ElsIf N=27 Then R=C.Get(New HTTPRequest("/query?a=1"));Return R.GetBodyAsString();
ElsIf N=28 Then R=C.Head(New HTTPRequest("/text"));Return String(R.StatusCode)+":"+String(R.GetBodyAsBinaryData().Size());
ElsIf N=29 Then Q.SetBodyFromString("я😀","UTF-8",ByteOrderMarkUse.DontUse);R=C.Post(Q);Return R.Headers.Get("X-Method")+":"+R.GetBodyAsString("UTF-8");
ElsIf N=30 Then Q.SetBodyFromBinaryData(Base64Value("AP9B"));R=C.Put(Q);Return R.Headers.Get("X-Method")+":"+Base64String(R.GetBodyAsBinaryData());
ElsIf N=31 Then Q.SetBodyFromString("patch","UTF-8",ByteOrderMarkUse.DontUse);R=C.Patch(Q);Return R.Headers.Get("X-Method")+":"+R.GetBodyAsString();
ElsIf N=32 Then Q.SetBodyFromString("delete","UTF-8",ByteOrderMarkUse.DontUse);R=C.Delete(Q);Return R.Headers.Get("X-Method")+":"+R.GetBodyAsString();
ElsIf N=33 Then R=C.CallHTTPMethod("OPTIONS",New HTTPRequest("/verbs"));Return String(R.StatusCode)+":"+R.GetBodyAsString();
ElsIf N=34 Then R=C.Get(New HTTPRequest("/redirect"));Return String(R.StatusCode)+":"+R.GetBodyAsString();
ElsIf N=35 Then R=C.Get(New HTTPRequest("/binary"));S=R.GetBodyAsStream();B=New BinaryDataBuffer(1);K=S.Read(B,0,1);V=String(S.CanRead)+":"+String(S.CanWrite)+":"+String(K)+":"+String(B.Get(0));S.Close();Return V;
ElsIf N=36 Then R=C.Get(New HTTPRequest("/binary"));S=R.GetBodyAsStream();T=R.GetBodyAsStream();S.Seek(1,PositionInStream.Begin);V=String(S.CurrentPosition())+":"+String(T.CurrentPosition())+":"+Base64String(R.GetBodyAsBinaryData());S.Close();T.Close();Return V;
ElsIf N=37 Then Return HTFile(N,C,Root);
ElsIf N=38 Then Return HTFile(N,C,Root);
ElsIf N=39 Then Return HTFile(N,C,Root);
ElsIf N=40 Then Return HTFile(N,C,Root);
EndIf;
EndFunction
Процедура HTObserve(N,C,Root)
L=Right("0"+String(N),2);
Try V=HTCase(N,C,Root);Except Сообщить("HT-"+L+": [action-error]");Return;EndTry;
Try R=HTEncode(V);Except Сообщить("HT-"+L+": [observer-error]");Return;EndTry;
Сообщить("HT-"+L+": [ok|"+R+"]");
EndProcedure
Процедура HTTPFamily(Port,OwnedRoot) Экспорт
If TypeOf(Port)<>Type("Number") Or Port<>Int(Port) Or Port<1024 Or Port>65535 Then Raise "port";EndIf;
E=New File(OwnedRoot);If Not E.IsDirectory() Then Raise "root";EndIf;
C=New HTTPConnection("127.0.0.1",Port,,,,10);
Сообщить("HT-C1: ["+HTEncode("")+"]");
Сообщить("HT-C2: ["+HTEncode("A ;""😀")+"]");
For N=1 To 40 Do HTObserve(N,C,OwnedRoot);EndDo;
EndProcedure
