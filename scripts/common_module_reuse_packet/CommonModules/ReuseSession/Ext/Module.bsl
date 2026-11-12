// Authored client-only reuse acquisition. Tokens identify executions, not expected answers.
Function Token(Key = "default") Export
 Return String(New UUID);
EndFunction
Function ChangeScalar(Key) Export
 Key = Key + 1;
 Return String(New UUID);
EndFunction
Function ChangeStructure(Value) Export
 Value.Seen = Value.Seen + 1;
 Return String(New UUID);
EndFunction
Function Mutable(Key) Export
 Value = New Array;
 Value.Add(String(New UUID));
 Return Value;
EndFunction
Function EmptyResult(Key) Export
 Return Undefined;
EndFunction
Function Failing(Key) Export
 Raise String(New UUID);
EndFunction
Procedure Touch(Val State) Export
 State.Seen = State.Seen + 1;
EndProcedure
Function InternalPair(Key) Export
 A = Token(Key); B = Token(Key);
 Return A = B;
EndFunction
Function QualifiedPair(Key) Export
 A = ReuseSession.Token(Key); B = ReuseSession.Token(Key);
 Return A = B;
EndFunction
