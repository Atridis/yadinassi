// !todo Passwords, exotic names/attributes, ZIP64 and source-close stream lifetime.
Функция ZFEncode(Val T)
If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "zip-observer-bound";EndIf;
R="S"+String(StrLen(T))+":";
For P=1 To StrLen(T) Do
C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "zip-unit-bound";EndIf;
For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;
R=R+H;
EndDo;
Return R;
EndFunction
Функция ZFBytes(Val Path)
B=GetBinaryDataBufferFromBinaryData(New BinaryData(Path));R="";
For I=0 To B.Size-1 Do R=R+String(B.Get(I))+",";EndDo;Return R;
EndFunction
Процедура ZFClean(Val Root)
For Each P In StrSplit("/out/sub/b.bin;/out/a.bin;/out/b.bin;/sub/b.bin;/a.bin;/x.zip",";") Do
F=New File(Root+P);If F.Exists() And F.IsFile() Then DeleteFiles(Root+P);EndIf;
EndDo;
For Each P In StrSplit("/out/out;/out/sub;/out;/sub;",";",True) Do
D=Root+P;F=New File(D);If F.Exists() Then A=FindFiles(D,"*");If A.Count()=0 Then DeleteFiles(D);EndIf;EndIf;
EndDo;
EndProcedure
Функция ZFCase(Val N)
Root=GetTempFileName("zip-family");F=New File(Root);If F.Exists() Then Raise "zip-fixture-collision";EndIf;
CreateDirectory(Root);W=Undefined;Z=Undefined;S=Undefined;R="";
Try
CreateDirectory(Root+"/sub");CreateDirectory(Root+"/out");
B=New BinaryDataBuffer(3);B.Set(0,65);B.Set(1,0);B.Set(2,255);D=GetBinaryDataFromBinaryDataBuffer(B);D.Write(Root+"/a.bin");
B.Set(0,66);GetBinaryDataFromBinaryDataBuffer(B).Write(Root+"/sub/b.bin");
Path=Root+"/x.zip";A=Root+"/a.bin";Q=Root+"/sub/b.bin";Out=Root+"/out";
If N=1 Then W=New ZipFileWriter(Path);W.Write();
ElsIf N=4 Then W=New ZipFileWriter(Path,"","ordinary");W.Add(A);W.Write();
ElsIf N=5 Then W=New ZipFileWriter(Path,"","",ZIPCompressionMethod.Copy);W.Add(A);W.Write();
ElsIf N=6 Then W=New ZipFileWriter(Path,"","",ZIPCompressionMethod.Deflate,ZIPCompressionLevel.Minimum);W.Add(A);W.Write();
ElsIf N=7 Then W=New ZipFileWriter(Path,"","",ZIPCompressionMethod.Deflate,ZIPCompressionLevel.Maximum);W.Add(A);W.Write();
ElsIf N=8 Then W=New ZipFileWriter(Path,"","",ZIPCompressionMethod.Deflate,ZIPCompressionLevel.Optimal);W.Add(A);W.Write();
ElsIf N=9 Then W=New ZipFileWriter;W.Open(Path,"","",ZIPCompressionMethod.Deflate,ZIPCompressionLevel.Optimal,ZIPEncryptionMethod.Zip20,FileNamesEncodingInZipFile.UTF8);W.Add(A);W.Write();
ElsIf N=10 Then W=New ZipFileWriter;W.Add(A);D=W.GetBinaryData();D.Write(Path);
ElsIf N=11 Then S=New MemoryStream;W=New ZipFileWriter(S);W.Add(A);W.Write();S.Seek(0,PositionInStream.Begin);Z=New ZipFileReader(S);
ElsIf N=23 Then W=New ZipFileWriter(Path);W.Add(Root+"/*.bin");W.Write();
ElsIf N=24 Or N=26 Then W=New ZipFileWriter(Path);W.Add(Root+"/*.bin",ZIPStorePathMode.StoreRelativePath,ZIPSubDirProcessingMode.ProcessRecursively);W.Write();
ElsIf N=25 Then W=New ZipFileWriter(Path);W.Add(Root+"/*.bin",ZIPStorePathMode.DontStorePath,ZIPSubDirProcessingMode.ProcessRecursively);W.Write();
ElsIf N=27 Then W=New ZipFileWriter;W.Open(Path);W.Add(A);W.Write();
Else W=New ZipFileWriter(Path);W.Add(A);If N=3 Or N=15 Or N=22 Or N=29 Then W.Add(Q);EndIf;W.Write();
EndIf;
If N=29 Then W=New ZipFileWriter(Path);W.Add(A);W.Write();EndIf;
If N=12 Then D=New BinaryData(Path);S=D.OpenStreamForRead();Z=New ZipFileReader(S);
ElsIf N=27 Then Z=New ZipFileReader;Z.Open(Path);
ElsIf N<>11 Then Z=New ZipFileReader(Path);
EndIf;
If N=1 Then R=String(Z.Items.Count());
ElsIf N=2 Then R=String(Z.Items.Count())+":"+Z.Items.Get(0).Name;
ElsIf N=3 Then R=String(Z.Items.Count())+":"+String(Z.Items.Find("b.bin")<>Undefined);
ElsIf N=4 Then R=Z.Comment;
ElsIf N=5 Then E=Z.Items.Get(0);R=String(E.CompressedSize=E.UncompressedSize)+":"+String(E.UncompressedSize);
ElsIf N=6 Or N=7 Or N=8 Or N=9 Or N=10 Or N=11 Or N=12 Then Z.ExtractAll(Out);R=ZFBytes(Out+"/a.bin");
ElsIf N=13 Then E=Z.Items.Get(0);R=E.Name+":"+E.BaseName+":"+E.Extension;
ElsIf N=14 Then R=String(Z.Items.Find("missing.bin")=Undefined);
ElsIf N=15 Then K=0;For Each E In Z.Items Do K=K+E.UncompressedSize;EndDo;R=String(K);
ElsIf N=16 Then R=String(Z.Items[0]=Z.Items.Get(0));
ElsIf N=17 Then E=Z.Items.Get(0);R=String(E.FullName=E.Name)+":"+String(E.OriginalName=E.Name);
ElsIf N=18 Then R=String(TypeOf(Z.Items.Get(0).Modified)=Type("Date"));
ElsIf N=19 Then R=String(Z.Items.Get(0).Encrypted);
ElsIf N=20 Then E=Z.Items.Get(0);R=String(E.UncompressedSize)+":"+String(E.CompressedSize>0);
ElsIf N=21 Then Z.Extract(Z.Items.Get(0),Out);R=ZFBytes(Out+"/a.bin");
ElsIf N=22 Then Z.ExtractAll(Out);R=ZFBytes(Out+"/a.bin")+":"+ZFBytes(Out+"/b.bin");
ElsIf N=23 Then R=String(Z.Items.Count());
ElsIf N=24 Then
R=String(Z.Items.Count());For Each E In Z.Items Do K=E.FullName;
If StrLen(K)>10 Then K="L"+String(StrLen(K))+"r"+String(StrFind(K,Root)>0);EndIf;
R=R+"|"+K;If E.UncompressedSize=0 Then R=R+"~";EndIf;EndDo;
Try Z.ExtractAll(Out);R=R+"|X";Except R=R+"|E";EndTry;
ElsIf N=25 Or N=26 Then Z.ExtractAll(Out,ZIPRestoreFilePathsMode.DontRestore);R=String(Z.Items.Count())+":"+ZFBytes(Out+"/b.bin");
ElsIf N=27 Then R=String(Z.Items.Count());
ElsIf N=28 Then Z.Close();Try Z.Close();R="close-ok";Except R="close-error";EndTry;
Try K=Z.Items.Count();R=R+":items"+String(K);Except R=R+":items-error";EndTry;Z=Undefined;
ElsIf N=29 Then R=String(Z.Items.Count())+":"+String(Z.Items.Find("b.bin")=Undefined);
ElsIf N=30 Then W=New ZipFileWriter;Try W.Add(Root+"/missing.bin");D=W.GetBinaryData();R="accepted";Except R="missing-error";EndTry;
ElsIf N=31 Then Try T=New ZipFileReader(Root+"/missing.zip");T.Close();R="unexpected";Except R="missing-error";EndTry;
ElsIf N=32 Then R=String(TypeOf(Z)=Type("ZipFileReader"))+":"+String(TypeOf(Z.Items)=Type("ZipFileEntries"))+":"+String(TypeOf(Z.Items.Get(0))=Type("ZipFileEntry"));
EndIf;
If Z<>Undefined Then Z.Close();EndIf;If S<>Undefined Then S.Close();EndIf;ZFClean(Root);If F.Exists() Then If N=24 Then Return "!cleanup";Else Raise "zip-fixture-cleanup";EndIf;EndIf;
Except
Try Z.Close();Except EndTry;Try S.Close();Except EndTry;Try ZFClean(Root);Except EndTry;Raise;
EndTry;
Return R;
EndFunction
Процедура ZFObserve(Val N)
Label=Right("0"+String(N),2);
Try V=ZFCase(N);Except Сообщить("ZF-"+Label+": [action-error]");Return;EndTry;
Try R=ZFEncode(V);Except Сообщить("ZF-"+Label+": [observer-error]");Return;EndTry;
Сообщить("ZF-"+Label+": [ok|"+R+"]");
EndProcedure
Сообщить("ZF-C1: ["+ZFEncode("")+"]");
Сообщить("ZF-C2: ["+ZFEncode("A ;""😀")+"]");
For N=1 To 32 Do ZFObserve(N);EndDo;
