// Independent compilation discriminator. A preprocessor command and annotation
// must BOTH admit the declaration to the same compilation side.
#If Client Then
&AtServer
Function AbsentOnBothSides()
    Return 42;
EndFunction
#EndIf

&AtClient
Procedure Probe() Export
    Message(AbsentOnBothSides());
EndProcedure
