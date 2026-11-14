Function ApplicationTitle() Export
 Return "Основная демо";
EndFunction
Function DefaultDraftTitle() Export
 Return "Новая операция";
EndFunction
Function Add(Val Value) Export
 Message("Calculated in the owned server process");
 Return Value + 1;
EndFunction
