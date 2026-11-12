// Owned native acquisition; no expected-result substitution.
Function Token(Val Key) Export
 Return String(New UUID);
EndFunction
Function InternalPair(Val Key) Export
 A = Token(Key); B = Token(Key);
 Return A = B;
EndFunction
