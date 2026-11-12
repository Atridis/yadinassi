Function MakeRecord(Kind) Export
Value=XDTOFactory.Create(Kind); Value.Code="module"; Return Value;
EndFunction
Function FactoryMatches(Value) Export
Return Value.Factory()=XDTOFactory;
EndFunction
