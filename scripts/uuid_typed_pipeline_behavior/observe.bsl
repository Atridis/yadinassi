// Изолированные UUID в типизированных коллекциях; только заданные константы.
Function FixedUUID()
 Return New УникальныйИдентификатор("11111111-2222-4333-8444-555555555555");
EndFunction
Function ZeroUUID()
 Return New УникальныйИдентификатор("00000000-0000-0000-0000-000000000000");
EndFunction
Function Bit(V)
 If V Then Return "1"; Else Return "0"; EndIf;
EndFunction
Function Cell(V)
 If TypeOf(V)=Type("УникальныйИдентификатор") Then
  If V=FixedUUID() Then Return "fixed"; EndIf;
  If V=ZeroUUID() Then Return "zero"; EndIf;
  Return "other_uuid";
 EndIf;
 If V=Undefined Then Return "undefined"; EndIf;
 If TypeOf(V)=Type("String") Then Return "string"; EndIf;
 Return "other_type";
EndFunction
Function RowsWitness(Matches,R)
 Result=String(Matches.Count());
 If Matches.Count()>0 Then Return Result+":"+Bit(Matches[0]=R); EndIf;
 Return Result+":empty";
EndFunction
Function BoundedWire(V)
 If TypeOf(V)<>Type("String") Or StrLen(V)>2048 Then Raise "owned-wire-bound"; EndIf;
 Return V;
EndFunction
Function TypedTable()
 T=New ValueTable; T.Columns.Add("U",New TypeDescription("УникальныйИдентификатор")); Return T;
EndFunction
Function AssignInputs(R)
 // Two independent conversions; readback remains outside the measured action catch.
 Rejected=False;
 Try R.U="11111111-2222-4333-8444-555555555555"; Except Rejected=True; EndTry;
 First=Bit(Rejected)+":"+Cell(R.U);
 R.U=FixedUUID(); Rejected=False;
 Try R.U=Undefined; Except Rejected=True; EndTry;
 Return First+":"+Bit(Rejected)+":"+Cell(R.U);
EndFunction
Function ObserveCase(CaseNo,Stage)
 Var UniqueLookupValue;
 If CaseNo=1 Then
  Stage="setup"; D=New TypeDescription("УникальныйИдентификатор");
  Stage="action";
  Try C=New TypeDescription(D);
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Bit(C.ContainsType(Type("УникальныйИдентификатор")))+":"+String(C.Types().Count()));
 EndIf;
 If CaseNo=2 Then
  Stage="setup"; A=New Array; A.Add(Type("УникальныйИдентификатор"));
  Stage="action";
  Try D=New TypeDescription(A);
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Bit(D.ContainsType(Type("УникальныйИдентификатор")))+":"+String(D.Types().Count()));
 EndIf;
 If CaseNo=3 Then
  Stage="setup"; T=New ValueTable;
  Stage="action";
  Try T.Columns.Add("U",New TypeDescription("УникальныйИдентификатор")); R=T.Add();
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Cell(R.U)+":"+String(T.Count()));
 EndIf;
 If CaseNo=4 Then
  Stage="setup"; T=TypedTable(); R=T.Add();
  Stage="action";
  Try R.U=FixedUUID();
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Cell(R.U)+":"+Bit(R.U=New УникальныйИдентификатор("11111111-2222-4333-8444-555555555555")));
 EndIf;
 If CaseNo=5 Then
  Stage="setup"; T=TypedTable(); R=T.Add(); R.U=FixedUUID();
  Stage="action";
  Result=AssignInputs(R);
  Stage="observe"; Return "S:"+(Result);
 EndIf;
 If CaseNo=6 Then
  Stage="setup"; T=TypedTable(); R=T.Add(); R.U=FixedUUID();
  Stage="action";
  Try C=T.Copy();
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Bit(C.Columns.U.ValueType.ContainsType(Type("УникальныйИдентификатор")))+":"+Cell(C[0].U)+":"+String(C.Count()));
 EndIf;
 If CaseNo=7 Then
  Stage="setup"; T=TypedTable(); R=T.Add(); R.U=FixedUUID(); T.Add();
  Stage="action";
  Try A=T.UnloadColumn("U"); C=TypedTable(); C.Add(); C.Add(); C.LoadColumn(A,"U");
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Cell(A[0])+":"+Cell(A[1])+":"+Cell(C[0].U)+":"+Cell(C[1].U));
 EndIf;
 If CaseNo=8 Then
  Stage="setup"; T=TypedTable(); T.Add(); T.Add();
  Stage="action";
  Try T.FillValues(FixedUUID(),"U");
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Cell(T[0].U)+":"+Cell(T[1].U));
 EndIf;
 If CaseNo=9 Then
  Stage="setup"; T=TypedTable(); R=T.Add(); R.U=FixedUUID(); T.Add(); UniqueLookupValue=New УникальныйИдентификатор("11111111-2222-4333-8444-555555555555");
  Stage="action";
  Try Found=T.Find(UniqueLookupValue,"U"); Matches=T.FindRows(New Structure("U",UniqueLookupValue));
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Bit(Found=R)+":"+RowsWitness(Matches,R));
 EndIf;
 If CaseNo=10 Then
  Stage="setup"; T=TypedTable(); R=T.Add(); R.U=FixedUUID(); T.Add(); UniqueLookupValue=New УникальныйИдентификатор("11111111-2222-4333-8444-555555555555");
  Stage="action";
  Try T.Indexes.Add("U"); Matches=T.FindRows(New Structure("U",UniqueLookupValue));
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(RowsWitness(Matches,R));
 EndIf;
 If CaseNo=11 Then
  Stage="setup"; T=New ValueTree; T.Columns.Add("U",New TypeDescription("УникальныйИдентификатор")); R=T.Rows.Add(); Child=R.Rows.Add();
  Stage="action";
  Try Child.U=FixedUUID();
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Cell(R.U)+":"+Cell(Child.U));
 EndIf;
 If CaseNo=12 Then
  Stage="setup"; T=New ValueTree; T.Columns.Add("U",New TypeDescription("УникальныйИдентификатор")); R=T.Rows.Add(); Child=R.Rows.Add(); Child.U=FixedUUID();
  Stage="action";
  Try C=T.Copy();
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Bit(C.Columns.U.ValueType.ContainsType(Type("УникальныйИдентификатор")))+":"+Cell(C.Rows[0].U)+":"+Cell(C.Rows[0].Rows[0].U));
 EndIf;
 If CaseNo=13 Then
  Stage="setup"; A=New Array; A.Add(FixedUUID()); A.Add(New Structure("U",ZeroUUID()));
  Stage="action";
  Try Encoded=ValueToStringInternal(A);
  Except Return "R:write"; EndTry;
  Stage="observe"; Encoded=BoundedWire(Encoded);
  Stage="action";
  Try C=ValueFromStringInternal(Encoded);
  Except Return "R:read/"+Encoded; EndTry;
  Stage="observe"; Return "S:"+(BoundedWire(Encoded)+"/"+Cell(C[0])+":"+Cell(C[1].U));
 EndIf;
 If CaseNo=14 Then
  Stage="setup"; M=New Map; M.Insert(FixedUUID(),ZeroUUID()); M.Insert(ZeroUUID(),FixedUUID()); F=New FixedMap(M); A=New Array; A.Add(M); A.Add(F);
  Stage="action";
  Try Encoded=ValueToStringInternal(A);
  Except Return "R:write"; EndTry;
  Stage="observe"; Encoded=BoundedWire(Encoded);
  Stage="action";
  Try C=ValueFromStringInternal(Encoded);
  Except Return "R:read/"+Encoded; EndTry;
  Stage="observe"; Return "S:"+(BoundedWire(Encoded)+"/"+Cell(C[0][FixedUUID()])+":"+Cell(C[1][ZeroUUID()]));
 EndIf;
 If CaseNo=15 Then
  Stage="setup"; A=New Array; A.Add(FixedUUID()); A.Add(New Structure("U",ZeroUUID()));
  Stage="action";
  Try Storage=New ValueStorage(A); C=Storage.Get();
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(Cell(C[0])+":"+Cell(C[1].U));
 EndIf;
 If CaseNo=16 Then
  Stage="setup"; Encoded=ValueToStringInternal(Type("УникальныйИдентификатор"));
  Stage="action";
  Try C=ValueFromStringInternal(Encoded);
  Except Return "R:action"; EndTry;
  Stage="observe"; Return "S:"+(BoundedWire(Encoded)+"/"+Bit(C=Type("УникальныйИдентификатор")));
 EndIf;
 Raise "unknown-owned-uuid-case";
EndFunction
For CaseNo = 1 To 16 Do
 Stage="setup";
 Try
  Value=ObserveCase(CaseNo,Stage); UUIDTypedPipelineEmit(CaseNo,Value);
 Except
  UUIDTypedPipelineDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
 EndTry;
EndDo;
