Function MakeRecord(Kind) Export
    Result=XDTOFactory.Create(Kind);
    Result.Title="module";
    Return Result;
EndFunction
Function FactoryMatches(Value) Export
    Return Value.Factory()=XDTOFactory;
EndFunction
