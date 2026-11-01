// !todo Async/exotic streams deferred. Owned files only; hashes are compatibility APIs.
Функция HFEncode(Val T)
 If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "hash-observer-bound";EndIf;
 R="S"+String(StrLen(T))+":";
 For P=1 To StrLen(T) Do
  C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "hash-unit-bound";EndIf;
  For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;R=R+H;
 EndDo;Return R;
EndFunction
Функция HFKey(Val X)
 If TypeOf(X)=Type("Number") Then Return String(X);EndIf;
 Return Base64String(X);
EndFunction
Функция HFAlgorithm(Val N)
 While N>5 Do N=N-5;EndDo;
 If N=1 Then Return HashFunction.CRC32;
 ElsIf N=2 Then Return HashFunction.MD5;
 ElsIf N=3 Then Return HashFunction.SHA1;
 ElsIf N=4 Then Return HashFunction.SHA256;
 Else Return HashFunction.SHA512;EndIf;
EndFunction
Функция HFVector(Val A,Val T,Val Expected)
 H=New DataHashing(A);H.Append(T);X=H.HashSum;
 If TypeOf(X)=Type("Number") Then Return String(X=Number(Expected))+":number";EndIf;
 Return String(Base64String(X)=Expected)+":"+String(X.Size());
EndFunction
Функция HFFile(Val N)
 Root=GetTempFileName("data-hashing");F=New File(Root);
 If F.Exists() Then Raise "hash-fixture-collision";EndIf;
 CreateDirectory(Root);Path=Root+"/a.bin";
 Try
  D=GetBinaryDataFromString("abc");D.Write(Path);
  H=New DataHashing(HFAlgorithm(N));H.Append("[");H.AppendFile(Path);H.Append("]");
  C=New DataHashing(HFAlgorithm(N));C.Append("[abc]");V=String(HFKey(H.HashSum)=HFKey(C.HashSum));
  Before=HFKey(H.HashSum);DeleteFiles(Path);
  Try H.AppendFile(Path);V=V+":unexpected";Except V=V+":missing";EndTry;
  V=V+":"+String(Before=HFKey(H.HashSum));
  Left=FindFiles(Root,"*");If Left.Count()<>0 Then Raise "hash-fixture-not-empty";EndIf;
  DeleteFiles(Root);If F.Exists() Then Raise "hash-fixture-cleanup";EndIf;
 Except
  Try DeleteFiles(Path);Except EndTry;
  Try Left=FindFiles(Root,"*");If Left.Count()=0 Then DeleteFiles(Root);EndIf;Except EndTry;
  Raise;
 EndTry;Return V;
EndFunction
Функция HFCase(Val N)
 If N=1 Then Return HFVector(HashFunction.CRC32,"","0");
 ElsIf N=2 Then Return HFVector(HashFunction.MD5,"","1B2M2Y8AsgTpgAmY7PhCfg==");
 ElsIf N=3 Then Return HFVector(HashFunction.SHA1,"","2jmj7l5rSw0yVb/vlWAYkK/YBwk=");
 ElsIf N=4 Then Return HFVector(HashFunction.SHA256,"","47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=");
 ElsIf N=5 Then Return HFVector(HashFunction.SHA512,"","z4PhNX7vuL3xVChQ1m2AB9Yg5AULVxXcg/SpIdNs6c5H0NE8XYXysP+DGNKHfuwvY7kxvUdBeoGlODJ6+SfaPg==");
 ElsIf N=6 Then H=New DataHashing(HashFunction.CRC32);H.Append("123456789");Return HFVector(HashFunction.CRC32,"abc","891568578")+":"+Format(H.HashSum,"ЧГ=0");
 ElsIf N=7 Then Return HFVector(HashFunction.MD5,"abc","kAFQmDzST7DWlj99KOF/cg==");
 ElsIf N=8 Then Return HFVector(HashFunction.SHA1,"abc","qZk+NkcGgWq6PiVxeFDCbJzQ2J0=");
 ElsIf N=9 Then Return HFVector(HashFunction.SHA256,"abc","ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=");
 ElsIf N=10 Then Return HFVector(HashFunction.SHA512,"abc","3a81oZNherrMQXNJriBBMRLm+k6JqX6iCp7u5ktV05ohkpkqJ0/BqDa6PCOj/uu9RU1EI2Q86A4qmslPpUyknw==");
 ElsIf N<=20 Then
  H=New DataHashing(HFAlgorithm(N));Empty=H.HashSum;H.Append("a");One=H.HashSum;
  A=HFKey(Empty);B=HFKey(One);H.Append("b");H.Append("c");C=New DataHashing(HFAlgorithm(N));C.Append("abc");
  If N<=15 Then Return String(HFKey(H.HashSum)=HFKey(C.HashSum))+":"+String(HFKey(H.HashSum)=HFKey(H.HashSum));EndIf;
  Return String(A=HFKey(Empty))+":"+String(B=HFKey(One))+":"+String(B<>HFKey(H.HashSum));
 EndIf;
 H=New DataHashing(HashFunction.SHA256);C=New DataHashing(HashFunction.SHA256);P=PositionInStream.Begin;
 If N=21 Then H.Append("яé");C.Append(GetBinaryDataFromString("яé"));Return String(HFKey(H.HashSum)=HFKey(C.HashSum));
 ElsIf N=22 Then H.Append("😀x");C.Append(GetBinaryDataFromString("😀x"));Return String(HFKey(H.HashSum)=HFKey(C.HashSum));
 ElsIf N=23 Then B=New BinaryDataBuffer(3);B.Set(0,0);B.Set(1,255);B.Set(2,65);D=GetBinaryDataFromBinaryDataBuffer(B);H.Append(D);S=D.OpenStreamForRead();C.Append(S);V=String(HFKey(H.HashSum)=HFKey(C.HashSum));S.Close();Return V;
 ElsIf N=24 Then H.Append("a");H.Append(GetBinaryDataFromString("b"));H.Append("c");C.Append("abc");Return String(HFKey(H.HashSum)=HFKey(C.HashSum));
 ElsIf N=25 Then S=GetBinaryDataFromString("abc").OpenStreamForRead();H.Append(S);C.Append("abc");V=String(HFKey(H.HashSum)=HFKey(C.HashSum))+":"+String(S.CurrentPosition())+":"+String(S.Size());S.Close();Return V;
 ElsIf N=26 Then S=GetBinaryDataFromString("abc").OpenStreamForRead();H.Append(S,2);C.Append("ab");V=String(HFKey(H.HashSum)=HFKey(C.HashSum))+":"+String(S.CurrentPosition());S.Close();Return V;
 ElsIf N=27 Then S=GetBinaryDataFromString("").OpenStreamForRead();Before=HFKey(H.HashSum);H.Append(S);V=String(Before=HFKey(H.HashSum))+":"+String(S.CurrentPosition());S.Close();Return V;
 ElsIf N=28 Then S=GetBinaryDataFromString("abc").OpenStreamForRead();H.Append(S,9);C.Append("abc");V=String(HFKey(H.HashSum)=HFKey(C.HashSum))+":"+String(S.CurrentPosition());H.Append(S);V=V+":"+String(HFKey(H.HashSum)=HFKey(C.HashSum));S.Close();Return V;
 ElsIf N=29 Then S=GetBinaryDataFromString("abc").OpenStreamForRead();S.Seek(1,P);H.Append(S);C.Append("bc");V=String(HFKey(H.HashSum)=HFKey(C.HashSum))+":"+String(S.CurrentPosition());S.Close();Return V;
 ElsIf N=30 Then S=New MemoryStream;S.Close();Before=HFKey(H.HashSum);Try H.Append(S);Return "unexpected";Except Return "closed:"+String(Before=HFKey(H.HashSum));EndTry;
 ElsIf N=31 Then S=New MemoryStream;GetBinaryDataFromString("abc").Write(S);S.Seek(0,P);T=S.GetReadonlyStream();H.Append(T,1);V=String(S.CurrentPosition())+":"+String(T.CurrentPosition())+":"+String(S.Size());T.Close();S.Close();Return V;
 ElsIf N=32 Then V="";Try H.HashFunction=HashFunction.MD5;V="unexpected";Except V="readonly";EndTry;Try H.HashSum=0;V=V+":unexpected";Except V=V+":readonly";EndTry;Return V;
 ElsIf N=33 Then Before=HFKey(H.HashSum);Try H.Append(5);Return "unexpected";Except Return "input:"+String(Before=HFKey(H.HashSum));EndTry;
 ElsIf N=34 Then S=New MemoryStream;Before=HFKey(H.HashSum);Try H.Append(S,-1);V="unexpected";Except V="count:"+String(Before=HFKey(H.HashSum));EndTry;S.Close();Return V;
 ElsIf N=35 Then V=String(TypeOf(H)=Type("DataHashing"))+":"+String(TypeOf(H.HashFunction)=Type("HashFunction"))+":"+String(H.HashFunction=HashFunction.SHA256);Try X=New DataHashing("SHA256");Return V+":unexpected";Except Return V+":constructor";EndTry;
 Else Return HFFile(N);EndIf;
EndFunction
Процедура HFObserve(Val N)
 L=Right("0"+String(N),2);
 Try V=HFCase(N);Except Сообщить("HF-"+L+": [action-error]");Return;EndTry;
 Try R=HFEncode(V);Except Сообщить("HF-"+L+": [observer-error]");Return;EndTry;
 Сообщить("HF-"+L+": [ok|"+R+"]");
EndProcedure
Сообщить("HF-C1: ["+HFEncode("")+"]");
Сообщить("HF-C2: ["+HFEncode("A ;""😀")+"]");
For N=1 To 40 Do HFObserve(N);EndDo;
