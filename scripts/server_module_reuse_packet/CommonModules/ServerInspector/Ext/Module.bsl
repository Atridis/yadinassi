// Owned native acquisition; no expected-result substitution.
Function DirectToken(Val Key) Export
 Return CachedServerCall.Token(Key);
EndFunction
Function SessionToken(Val Key) Export
 Return ServerSession.Token(Key);
EndFunction
Function SessionPair(Val Key) Export
 A = ServerSession.Token(Key); B = ServerSession.Token(Key);
 Return A = B;
EndFunction
Function InternalPair(Val Key) Export
 Return ServerSession.InternalPair(Key);
EndFunction
Function RequestPair(Val Key) Export
 A = ServerRequest.Token(Key); B = ServerRequest.Token(Key);
 Return A = B;
EndFunction
Function RequestToken(Val Key) Export
 Return ServerRequest.Token(Key);
EndFunction
Procedure RefreshServer() Export
 RefreshReusableValues();
EndProcedure
