// !todo Async/exotic encodings deferred. Owned files.
Функция DFEncode(Val T)
 If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "data-observer-bound";EndIf;
 R="S"+String(StrLen(T))+":";
 For P=1 To StrLen(T) Do
  C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "data-unit-bound";EndIf;
  For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;
  R=R+H;
 EndDo;Return R;
EndFunction
Функция DFReader(Val T)
 Return New DataReader(GetBinaryDataFromString(T));
EndFunction
Функция DFText(Val X)
 Return GetStringFromBinaryData(X.GetBinaryData());
EndFunction
Функция DFFile(Val N)
 Root=GetTempFileName("data-io");F=New File(Root);
 If F.Exists() Then Raise "data-fixture-collision";EndIf;
 CreateDirectory(Root);Path=Root+"/a.bin";W=Undefined;R=Undefined;
 Try
  W=New DataWriter(Path);W.WriteChars("ab");W.Close();
  If N=36 Then
   R=New DataReader(Path);V=R.ReadChars()+":"+String(R.ReadCompleted);R.Close();
  ElsIf N=37 Then
   W=New DataWriter(Path,,,,True);W.WriteChars("я");W.Close();R=New DataReader(Path);V=R.ReadChars();R.Close();
  ElsIf N=38 Then
   W=New DataWriter(Path,"UTF-16",,,, ,True);W.WriteChars("я");W.Close();R=New DataReader(Path,"UTF-16");V=R.ReadChars();R.Close();
  ElsIf N=39 Then
   R=New DataReader(Path);S=R.SourceStream();R.Close();Try S.Size();V="unexpected";Except V="owned-closed";EndTry;
  ElsIf N=40 Then
   W=New DataWriter(Path);S=W.TargetStream();W.WriteChars("x");W.Close();Try S.Size();V="unexpected";Except V="owned-closed";EndTry;R=New DataReader(Path);V=V+":"+R.ReadChars();R.Close();
  EndIf;
  DeleteFiles(Path);Left=FindFiles(Root,"*");If Left.Count()<>0 Then Raise "data-fixture-not-empty";EndIf;
  DeleteFiles(Root);If F.Exists() Then Raise "data-fixture-cleanup";EndIf;
 Except
  Try W.Close();Except EndTry;Try R.Close();Except EndTry;
  Try DeleteFiles(Path);Except EndTry;
  Try Left=FindFiles(Root,"*");If Left.Count()=0 Then DeleteFiles(Root);EndIf;Except EndTry;
  Raise;
 EndTry;Return V;
EndFunction
Функция DFCase(Val N)
 S=New MemoryStream;W=New DataWriter(S);P=PositionInStream.Begin;
 If N=1 Then W.WriteByte(255);W.Close();S.Seek(0,P);R=New DataReader(S);Return String(R.ReadByte())+":"+String(R.ReadByte()=Undefined);
 ElsIf N=2 Then W.WriteInt16(258);W.WriteInt16(258,ByteOrder.BigEndian);W.Close();S.Seek(0,P);R=New DataReader(S);A=R.ReadInt16();R.ByteOrder=ByteOrder.BigEndian;Return String(A)+":"+String(R.ReadInt16());
 ElsIf N=3 Then W.WriteInt32(4294967295);W.Close();S.Seek(0,P);R=New DataReader(S);Return String(R.ReadInt32()=4294967295);
 ElsIf N=4 Then W.WriteInt64(18446744073709551615,ByteOrder.BigEndian);W.Close();S.Seek(0,P);R=New DataReader(S);Return String(R.ReadInt64(ByteOrder.BigEndian)=18446744073709551615);
 ElsIf N=5 Then W.Close();W=New DataWriter(S,,ByteOrder.BigEndian);W.WriteInt16(258);W.Close();S.Seek(0,P);R=New DataReader(S);Return String(R.ReadByte())+":"+String(R.ReadByte());
 ElsIf N=6 Then W.WriteByte(7);W.Close();S.Seek(0,P);R=New DataReader(S);A=R.ReadInt16();Return String(A=Undefined)+":"+String(S.CurrentPosition())+":"+String(R.ReadCompleted);
 ElsIf N=7 Then B=New BinaryDataBuffer(3);B.Set(0,65);B.Set(1,66);B.Set(2,67);W.WriteBinaryDataBuffer(B);W.WriteBinaryDataBuffer(B,1,1);W.Close();S.Seek(0,P);R=New DataReader(S);C=R.ReadIntoBinaryDataBuffer();Return String(C.Size)+":"+String(C.Get(3));
 ElsIf N=8 Then R=DFReader("ab");B=New BinaryDataBuffer(4);K=R.ReadIntoBinaryDataBuffer(B,1,3);Return String(K)+":"+String(B.Get(1))+":"+String(B.Get(2));
 ElsIf N=9 Then R=DFReader("abc");X=R.Read(2);Return DFText(X)+":"+String(X.Size)+":"+String(X.MarkerFound)+":"+String(X.MarkerIndex);
 ElsIf N=10 Then R=DFReader("a");A=R.ReadCompleted;X=R.Read(1);B=R.ReadCompleted;X=R.Read(1);Return String(A)+":"+String(B)+":"+String(R.ReadCompleted)+":"+String(X.Size);
 ElsIf N=11 Then R=DFReader("ab");X=R.Read();B=X.GetBinaryDataBuffer();B.Set(0,90);Return DFText(X)+":"+String(X.GetBinaryDataBuffer().Get(0));
 ElsIf N=12 Then R=DFReader("ab");X=R.Read();A=X.OpenStreamForRead();B=X.OpenStreamForRead();A.Seek(1,P);V=String(A.CurrentPosition())+":"+String(B.CurrentPosition())+":"+String(A.CanWrite);A.Close();B.Close();Return V;
 ElsIf N=13 Then R=DFReader("bc");W.Write(GetBinaryDataFromString("a"));W.Write(R.Read());W.Close();S.Seek(0,P);R=New DataReader(S);Return R.ReadChars();
 ElsIf N=14 Then R=DFReader("abc");K=R.CopyTo(S,2);S.Seek(0,P);T=New DataReader(S);Return String(K)+":"+T.ReadChars()+":"+R.ReadChars();
 ElsIf N=15 Then R=DFReader("abc");K=R.CopyTo(W);W.Close();S.Seek(0,P);R=New DataReader(S);Return String(K)+":"+R.ReadChars();
 ElsIf N=16 Then R=DFReader("abc");A=R.Skip(2);B=R.Skip(9);Return String(A)+":"+String(B)+":"+String(R.ReadCompleted);
 ElsIf N=17 Then R=DFReader("яab");A=R.ReadChars(2);Return A+":"+R.ReadChars();
 ElsIf N=18 Then R=DFReader("😀x");A=R.ReadChars(1);B=R.ReadChars(1);Return A+":"+B+":"+R.ReadChars();
 ElsIf N=19 Then R=DFReader("a"+Chars.CR+Chars.LF+"b"+Chars.LF);Return R.ReadLine()+":"+R.ReadLine()+":"+String(R.ReadLine()=Undefined);
 ElsIf N=20 Then R=DFReader("a||b||");R.LineSplitter="||";Return R.ReadLine()+":"+R.ReadLine()+":"+String(R.ReadLine()=Undefined);
 ElsIf N=21 Then W.LineSplitter="!";W.WriteLine("я");W.WriteLine("x",,"?");W.Close();S.Seek(0,P);R=New DataReader(S);Return R.ReadChars();
 ElsIf N=22 Then W.TextEncoding="UTF-16LE";W.WriteChars("я");W.WriteChars("x","UTF-8");W.Close();S.Seek(0,P);R=New DataReader(S,"UTF-16LE");A=R.ReadChars(1);Return A+":"+R.ReadChars(1,"UTF-8");
 ElsIf N=23 Then W.Close();W=New DataWriter(S,"UTF-8",,,,True);W.WriteChars("a");W.Close();S.Seek(0,P);R=New DataReader(S);Return String(R.ReadByte())+":"+String(R.ReadByte())+":"+String(R.ReadByte())+":"+String(R.ReadByte());
 ElsIf N=24 Then W.ConvertibleSplitterOfLines="<>";W.WriteChars("a"+Chars.LF+"b");W.Close();S.Seek(0,P);R=New DataReader(S);R.ConvertedLineDelimiter="<>";Return R.ReadChars();
 ElsIf N=25 Then W.WriteByte(65);W.Close();A=S.Size();S.Seek(0,P);R=New DataReader(S);R.Close();Return String(A)+":"+String(S.Size());
 ElsIf N=26 Then R=New DataReader(S);Return String(R.SourceStream()=S)+":"+String(W.TargetStream()=S);
 ElsIf N=27 Then R=DFReader("ab::cd");X=R.ReadTo("::");Return DFText(X)+":"+String(X.MarkerFound)+":"+String(X.MarkerIndex)+":"+R.ReadChars();
 ElsIf N=28 Then R=DFReader("a|b");B=New BinaryDataBuffer(1);B.Set(0,124);X=R.ReadTo(B);Return DFText(X)+":"+String(X.MarkerIndex)+":"+R.ReadChars();
 ElsIf N=29 Then R=DFReader("a::b");M=New Array;M.Add(":");M.Add("::");X=R.ReadTo(M);Return DFText(X)+":"+String(X.MarkerIndex)+":"+R.ReadChars();
 ElsIf N=30 Then R=DFReader("abc");X=R.ReadTo("!");Return DFText(X)+":"+String(X.MarkerFound)+":"+String(X.MarkerIndex);
 ElsIf N=31 Then R=DFReader("a::b");M=New Array;M.Add("!");M.Add("::");A=R.SkipTo(M);B=R.ReadChars();Return String(A)+":"+B+":"+String(R.SkipTo("!"));
 ElsIf N=32 Then R=DFReader("a||b|");A=R.Split("|");V=String(A.Count())+":";For Each X In A Do V=V+DFText(X)+",";EndDo;Return V;
 ElsIf N=33 Then R=DFReader("a:b|c");M=New Array;M.Add(":");B=New BinaryDataBuffer(1);B.Set(0,124);M.Add(B);A=R.Split(M);V="";For Each X In A Do V=V+DFText(X)+":"+String(X.MarkerIndex)+",";EndDo;Return V;
 ElsIf N=34 Then R=DFReader("abcde");A=R.SplitInPartsOf(2);V="";For Each X In A Do V=V+DFText(X)+":"+String(X.Size)+",";EndDo;Return V;
 ElsIf N=35 Then R=DFReader("a");X=R.Read();Return String(TypeOf(R)=Type("DataReader"))+":"+String(TypeOf(W)=Type("DataWriter"))+":"+String(TypeOf(X)=Type("ReadDataResult"));
 Else W.Close();S.Close();Return DFFile(N);
 EndIf;
EndFunction
Процедура DFObserve(Val N)
 L=Right("0"+String(N),2);
 Try V=DFCase(N);Except Сообщить("DF-"+L+": [action-error]");Return;EndTry;
 Try R=DFEncode(V);Except Сообщить("DF-"+L+": [observer-error]");Return;EndTry;
 Сообщить("DF-"+L+": [ok|"+R+"]");
EndProcedure
Сообщить("DF-C1: ["+DFEncode("")+"]");
Сообщить("DF-C2: ["+DFEncode("A ;""😀")+"]");
For N=1 To 40 Do DFObserve(N);EndDo;
