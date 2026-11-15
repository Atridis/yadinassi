// Owned native acquisition; no expected-result substitution.
Function Token(Val Key) Export
 Return String(New UUID);
EndFunction
Function Failing(Val Key) Export
 Raise String(New UUID);
EndFunction
