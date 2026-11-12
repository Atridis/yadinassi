Function CPMaskEN()
 Value = 0;
#If Client Then
 Value = Value + 1;
#EndIf
#If Server Then
 Value = Value + 2;
#EndIf
#If AtClient Then
 Value = Value + 4;
#EndIf
#If AtServer Then
 Value = Value + 8;
#EndIf
#If ThickClientManagedApplication Then
 Value = Value + 16;
#EndIf
#If ThickClientOrdinaryApplication Then
 Value = Value + 32;
#EndIf
#If ThinClient Then
 Value = Value + 64;
#EndIf
#If WebClient Then
 Value = Value + 128;
#EndIf
#If ExternalConnection Then
 Value = Value + 256;
#EndIf
 Return String(Value);
EndFunction
Function CPMaskRU()
 Value = 0;
#If Клиент Then
 Value = Value + 1;
#EndIf
#If Сервер Then
 Value = Value + 2;
#EndIf
#If НаКлиенте Then
 Value = Value + 4;
#EndIf
#If НаСервере Then
 Value = Value + 8;
#EndIf
#If ТолстыйКлиентУправляемоеПриложение Then
 Value = Value + 16;
#EndIf
#If ТолстыйКлиентОбычноеПриложение Then
 Value = Value + 32;
#EndIf
#If ТонкийКлиент Then
 Value = Value + 64;
#EndIf
#If ВебКлиент Then
 Value = Value + 128;
#EndIf
#If ВнешнееСоединение Then
 Value = Value + 256;
#EndIf
 Return String(Value);
EndFunction
Function CPMobileEN()
 Value = 0;
#If MobileAppClient Then
 Value = Value + 1;
#EndIf
#If MobileAppServer Then
 Value = Value + 2;
#EndIf
 Return String(Value);
EndFunction
Function CPMobileRU()
 Value = 0;
#If МобильноеПриложениеКлиент Then
 Value = Value + 1;
#EndIf
#If МобильноеПриложениеСервер Then
 Value = Value + 2;
#EndIf
 Return String(Value);
EndFunction
