// Owned files only.
// !todo Async/bitwise/split, sharing locks and unspecified growth bytes are deferred.
Функция BFEncode(Val T)
 If TypeOf(T) <> Type("String") Or StrLen(T) > 40 Then Raise "buffer-observer-bound"; EndIf;
 R = "S" + String(StrLen(T)) + ":";
 For P = 1 To StrLen(T) Do
  C = CharCode(T, P); H = "";
  If C < 0 Or C > 65535 Then Raise "buffer-unit-bound"; EndIf;
  For D = 1 To 4 Do Q = Int(C / 16); H = Mid("0123456789abcdef", C-Q*16+1, 1)+H; C=Q; EndDo;
  R=R+H;
 EndDo;
 Return R;
EndFunction
Функция BFBytes(Val B)
 R=""; For I=0 To B.Size-1 Do R=R+String(B.Get(I))+","; EndDo; Return R;
EndFunction
Функция BFFile(Val N)
 Root=GetTempFileName("binary-stream"); F=New File(Root);
 If F.Exists() Then Raise "buffer-fixture-collision"; EndIf;
 CreateDirectory(Root); Path=Root+"/a.bin"; S=Undefined; R="";
 Try
  B=New BinaryDataBuffer(3); B.Set(0,65); B.Set(1,66); B.Set(2,67);
  S=New FileStream(Path,FileOpenMode.CreateNew); S.Write(B,0,3); S.Close();
  If N=33 Then
   S=New FileStream(Path,FileOpenMode.Open,FileAccess.ReadAndWrite); S.Seek(1); B.Set(0,90); S.Write(B,0,1); S.Flush(); S.Seek(0); C=New BinaryDataBuffer(3); K=S.Read(C,0,3); R=String(K)+":"+BFBytes(C);
  ElsIf N=34 Then
   S=New FileStream(Path,FileOpenMode.Append); R=String(S.CurrentPosition()); S.Write(B,0,1); R=R+":"+String(S.Size());
  ElsIf N=35 Then
   S=New FileStream(Path,FileOpenMode.OpenOrCreate); S.Write(B,0,1); R=String(S.Size())+":"+String(S.CurrentPosition());
  ElsIf N=36 Then
   S=New FileStream(Path,FileOpenMode.Truncate); R=String(S.Size()); S.Write(B,0,2); R=R+":"+String(S.Size());
  ElsIf N=37 Then
   Try S=New FileStream(Path,FileOpenMode.CreateNew); R="unexpected"; Except R="exists-error"; EndTry;
  ElsIf N=38 Then
   S=New FileStream(Path,FileOpenMode.Open,FileAccess.Read); R=String(S.CanRead)+":"+String(S.CanWrite); Try S.Write(B,0,1); R=R+":unexpected"; Except R=R+":write-error"; EndTry;
  ElsIf N=39 Then
   S=New FileStream(Path,FileOpenMode.Create); R=String(S.Size())+":"+String(S.CanRead)+":"+String(S.CanWrite); S.Write(B,0,3); S.Seek(0); M=New MemoryStream; K=S.CopyTo(M); R=R+":"+String(K); M.Close();
  ElsIf N=40 Then
   S=New FileStream(Path,FileOpenMode.Open,FileAccess.Write); R=String(S.CanRead)+":"+String(S.CanWrite)+":"+String(Right(S.FileName,5)="a.bin"); S.Close(); S.Close(); Try S.Size(); R=R+":unexpected"; Except R=R+":closed"; EndTry;
  EndIf;
  S.Close(); DeleteFiles(Path); Remaining=FindFiles(Root,"*");
  If Remaining.Count()<>0 Then Raise "buffer-fixture-not-empty"; EndIf;
  DeleteFiles(Root); If F.Exists() Then Raise "buffer-fixture-cleanup"; EndIf;
 Except
  Try S.Close(); Except EndTry;
  Try DeleteFiles(Path); Except EndTry;
  Try Remaining=FindFiles(Root,"*"); If Remaining.Count()=0 Then DeleteFiles(Root); EndIf; Except EndTry;
  Raise;
 EndTry;
 Return R;
EndFunction
Функция BFCase(Val N)
 B=New BinaryDataBuffer(8);
 If N=1 Then Return String(B.Size)+":"+String(B.ReadOnly)+":"+String(B.ByteOrder=ByteOrder.LittleEndian);
 ElsIf N=2 Then B.Set(0,0); B.Set(1,255); Return String(B.Get(0))+":"+String(B.Get(1));
 ElsIf N=3 Then B.WriteInt16(1,258); Return String(B.ReadInt16(1))+":"+String(B.Get(1))+":"+String(B.Get(2));
 ElsIf N=4 Then B.ByteOrder=ByteOrder.BigEndian; B.WriteInt16(0,258); Return String(B.Get(0))+":"+String(B.Get(1))+":"+String(B.ReadInt16(0,ByteOrder.LittleEndian));
 ElsIf N=5 Then B.WriteInt32(0,4294967295); Return String(B.ReadInt32(0)=4294967295)+":"+String(B.Get(3));
 ElsIf N=6 Then B.WriteInt64(0,18446744073709551615,ByteOrder.BigEndian); Return String(B.ReadInt64(0,ByteOrder.BigEndian)=18446744073709551615);
 ElsIf N=7 Then B.Set(2,11); C=B.GetSlice(2,2); C.Set(0,22); B.Set(3,33); Return String(B.Get(2))+":"+BFBytes(C);
 ElsIf N=8 Then B.Set(0,11); C=B.Read(0,1).Copy(); C.Set(0,22); Return String(B.Get(0))+":"+String(C.Get(0));
 ElsIf N=9 Then C=New BinaryDataBuffer(2); C.Set(0,1); C.Set(1,2); D=C.Reverse().Concat(C); Return BFBytes(D)+":"+BFBytes(C);
 ElsIf N=10 Then C=New BinaryDataBuffer(2); C.Set(0,4); C.Set(1,5); B.Write(2,C); Return String(B.Get(2))+":"+String(B.Get(3));
 ElsIf N=11 Then B.SetReadOnly(); Try B.Set(0,1); Return "unexpected"; Except Return String(B.ReadOnly)+":write-error"; EndTry;
 ElsIf N=12 Then Try B.Set(8,1); Return "unexpected"; Except Return "bounds-error"; EndTry;
 ElsIf N=13 Then S=New MemoryStream; R=String(S.Size())+":"+String(S.CurrentPosition())+":"+String(S.CanRead And S.CanWrite And S.CanSeek); S.Close(); Return R;
 ElsIf N=14 Then S=New MemoryStream(64); R=String(S.Size())+":"+String(S.CurrentPosition()); S.Close(); Return R;
 ElsIf N=15 Then S=New MemoryStream; B.Set(0,9); S.Write(B,0,1); R=String(S.Size())+":"+String(S.CurrentPosition()); S.Close(); Return R;
 ElsIf N=16 Then S=New MemoryStream; B.Set(0,7); S.Write(B,0,1); S.Seek(0); C=New BinaryDataBuffer(3); K=S.Read(C,1,3-1); R=String(K)+":"+String(C.Get(1))+":"+String(S.Read(C,0,1)); S.Close(); Return R;
 ElsIf N=17 Then S=New MemoryStream(B); S.Seek(5); R=String(S.Seek(2))+":"+String(S.CurrentPosition()); S.Close(); Return R;
 ElsIf N=18 Then S=New MemoryStream(B); S.Seek(3); R=String(S.Seek(2,PositionInStream.Current))+":"+String(S.Seek(-1,PositionInStream.End)); S.Close(); Return R;
 ElsIf N=19 Then S=New MemoryStream; S.Write(B,0,8); S.Seek(7); S.SetSize(3); R=String(S.Size())+":"+String(S.CurrentPosition()); S.Close(); Return R;
 ElsIf N=20 Then S=New MemoryStream; S.SetSize(12); R=String(S.Size()); S.Close(); Return R;
 ElsIf N=21 Then S=New MemoryStream(B); S.Seek(2); D=New MemoryStream; K=S.CopyTo(D,3); R=String(K)+":"+String(S.CurrentPosition())+":"+String(D.CurrentPosition()); S.Close(); D.Close(); Return R;
 ElsIf N=22 Then S=New MemoryStream(B); S.Seek(6); D=New MemoryStream; K=S.CopyTo(D); R=String(K)+":"+String(D.Size()); S.Close(); D.Close(); Return R;
 ElsIf N=23 Then S=New MemoryStream(B); C=New BinaryDataBuffer(1); C.Set(0,44); S.Write(C,0,1); B.Set(1,55); S.Seek(1); S.Read(C,0,1); R=String(B.Get(0))+":"+String(C.Get(0)); S.Close(); Return R;
 ElsIf N=24 Then S=New MemoryStream(B); S.Seek(8); Try S.Write(B,0,1); R="unexpected"; Except R="capacity-error"; EndTry; S.Close(); Return R;
 ElsIf N=25 Then B.SetReadOnly(); S=New MemoryStream(B); R=String(S.CanWrite); Try S.Write(B,0,1); R=R+":unexpected"; Except R=R+":write-error"; EndTry; S.Close(); Return R;
 ElsIf N=26 Then S=New MemoryStream(B); D=S.GetReadonlyStream(); D.Seek(3); R=String(S.CurrentPosition())+":"+String(D.CanWrite); D.Close(); S.Close(); Return R;
 ElsIf N=27 Then S=New MemoryStream(B); D=S.GetReadonlyStream(); D.Close(); Try R=String(S.Size()); Except R="base-closed"; EndTry; S.Close(); Return R;
 ElsIf N=28 Then S=New MemoryStream; S.Close(); S.Close(); Try S.Size(); Return "unexpected"; Except Return "closed"; EndTry;
 ElsIf N=29 Then S=New MemoryStream; B.Set(0,65); S.Write(B,0,1); D=S.CloseAndGetBinaryData(); S=New MemoryStream; D.Write(S); D=S.CloseAndGetBinaryData(); Return String(D.Size())+":"+String(GetBinaryDataBufferFromBinaryData(D).Get(0));
 ElsIf N=30 Then D=GetBinaryDataFromBinaryDataBuffer(B); S=D.OpenStreamForRead(); T=D.OpenStreamForRead(); S.Seek(3); R=String(S.CurrentPosition())+":"+String(T.CurrentPosition())+":"+String(S.CanWrite); S.Close(); T.Close(); Return R;
 ElsIf N=31 Then B.Set(0,11); D=GetBinaryDataFromBinaryDataBuffer(B); C=GetBinaryDataBufferFromBinaryData(D); B.Set(0,22); C.Set(0,33); E=GetBinaryDataBufferFromBinaryData(D); Return String(E.Get(0))+":"+String(C.Get(0));
 ElsIf N=32 Then S=New MemoryStream; R=String(TypeOf(B)=Type("BinaryDataBuffer"))+":"+String(TypeOf(S)=Type("MemoryStream"))+":"+String(TypeOf(ByteOrder.BigEndian)=Type("ByteOrder")); S.Close(); Return R;
 Else Return BFFile(N);
 EndIf;
EndFunction
Процедура BFObserve(Val N)
 Label=Right("0"+String(N),2);
 Try V=BFCase(N); Except Сообщить("BF-"+Label+": [action-error]"); Return; EndTry;
 Try R=BFEncode(V); Except Сообщить("BF-"+Label+": [observer-error]"); Return; EndTry;
 Сообщить("BF-"+Label+": [ok|"+R+"]");
EndProcedure
Сообщить("BF-C1: ["+BFEncode("")+"]");
Сообщить("BF-C2: ["+BFEncode("A ;""😀")+"]");
For N=1 To 40 Do BFObserve(N); EndDo;
