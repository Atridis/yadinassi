// BEGIN bounded preprocessor profile observation
// Direct literal compilation at each site; never infer flags from execution side.
&AtClient
Function PPClient()
    Var EnglishMask, RussianMask;
    EnglishMask = 0;
    RussianMask = 0;
#If Client Then
    EnglishMask = EnglishMask + 1;
#EndIf
#Если Клиент Тогда
    RussianMask = RussianMask + 1;
#КонецЕсли
#If Server Then
    EnglishMask = EnglishMask + 2;
#EndIf
#Если Сервер Тогда
    RussianMask = RussianMask + 2;
#КонецЕсли
#If AtClient Then
    EnglishMask = EnglishMask + 4;
#EndIf
#Если НаКлиенте Тогда
    RussianMask = RussianMask + 4;
#КонецЕсли
#If AtServer Then
    EnglishMask = EnglishMask + 8;
#EndIf
#Если НаСервере Тогда
    RussianMask = RussianMask + 8;
#КонецЕсли
#If ThinClient Then
    EnglishMask = EnglishMask + 16;
#EndIf
#Если ТонкийКлиент Тогда
    RussianMask = RussianMask + 16;
#КонецЕсли
#If WebClient Then
    EnglishMask = EnglishMask + 32;
#EndIf
#Если ВебКлиент Тогда
    RussianMask = RussianMask + 32;
#КонецЕсли
#If ThickClientOrdinaryApplication Then
    EnglishMask = EnglishMask + 64;
#EndIf
#Если ТолстыйКлиентОбычноеПриложение Тогда
    RussianMask = RussianMask + 64;
#КонецЕсли
#If ThickClientManagedApplication Then
    EnglishMask = EnglishMask + 128;
#EndIf
#Если ТолстыйКлиентУправляемоеПриложение Тогда
    RussianMask = RussianMask + 128;
#КонецЕсли
#If ExternalConnection Then
    EnglishMask = EnglishMask + 256;
#EndIf
#Если ВнешнееСоединение Тогда
    RussianMask = RussianMask + 256;
#КонецЕсли
    Return PPEncode(EnglishMask) + PPEncode(RussianMask);
EndFunction

&AtServer
Function PPServer()
    Var EnglishMask, RussianMask;
    EnglishMask = 0;
    RussianMask = 0;
#If Client Then
    EnglishMask = EnglishMask + 1;
#EndIf
#Если Клиент Тогда
    RussianMask = RussianMask + 1;
#КонецЕсли
#If Server Then
    EnglishMask = EnglishMask + 2;
#EndIf
#Если Сервер Тогда
    RussianMask = RussianMask + 2;
#КонецЕсли
#If AtClient Then
    EnglishMask = EnglishMask + 4;
#EndIf
#Если НаКлиенте Тогда
    RussianMask = RussianMask + 4;
#КонецЕсли
#If AtServer Then
    EnglishMask = EnglishMask + 8;
#EndIf
#Если НаСервере Тогда
    RussianMask = RussianMask + 8;
#КонецЕсли
#If ThinClient Then
    EnglishMask = EnglishMask + 16;
#EndIf
#Если ТонкийКлиент Тогда
    RussianMask = RussianMask + 16;
#КонецЕсли
#If WebClient Then
    EnglishMask = EnglishMask + 32;
#EndIf
#Если ВебКлиент Тогда
    RussianMask = RussianMask + 32;
#КонецЕсли
#If ThickClientOrdinaryApplication Then
    EnglishMask = EnglishMask + 64;
#EndIf
#Если ТолстыйКлиентОбычноеПриложение Тогда
    RussianMask = RussianMask + 64;
#КонецЕсли
#If ThickClientManagedApplication Then
    EnglishMask = EnglishMask + 128;
#EndIf
#Если ТолстыйКлиентУправляемоеПриложение Тогда
    RussianMask = RussianMask + 128;
#КонецЕсли
#If ExternalConnection Then
    EnglishMask = EnglishMask + 256;
#EndIf
#Если ВнешнееСоединение Тогда
    RussianMask = RussianMask + 256;
#КонецЕсли
    Return PPEncode(EnglishMask) + PPEncode(RussianMask);
EndFunction

&AtServerNoContext
Function PPServerNoContext()
    Var EnglishMask, RussianMask;
    EnglishMask = 0;
    RussianMask = 0;
#If Client Then
    EnglishMask = EnglishMask + 1;
#EndIf
#Если Клиент Тогда
    RussianMask = RussianMask + 1;
#КонецЕсли
#If Server Then
    EnglishMask = EnglishMask + 2;
#EndIf
#Если Сервер Тогда
    RussianMask = RussianMask + 2;
#КонецЕсли
#If AtClient Then
    EnglishMask = EnglishMask + 4;
#EndIf
#Если НаКлиенте Тогда
    RussianMask = RussianMask + 4;
#КонецЕсли
#If AtServer Then
    EnglishMask = EnglishMask + 8;
#EndIf
#Если НаСервере Тогда
    RussianMask = RussianMask + 8;
#КонецЕсли
#If ThinClient Then
    EnglishMask = EnglishMask + 16;
#EndIf
#Если ТонкийКлиент Тогда
    RussianMask = RussianMask + 16;
#КонецЕсли
#If WebClient Then
    EnglishMask = EnglishMask + 32;
#EndIf
#Если ВебКлиент Тогда
    RussianMask = RussianMask + 32;
#КонецЕсли
#If ThickClientOrdinaryApplication Then
    EnglishMask = EnglishMask + 64;
#EndIf
#Если ТолстыйКлиентОбычноеПриложение Тогда
    RussianMask = RussianMask + 64;
#КонецЕсли
#If ThickClientManagedApplication Then
    EnglishMask = EnglishMask + 128;
#EndIf
#Если ТолстыйКлиентУправляемоеПриложение Тогда
    RussianMask = RussianMask + 128;
#КонецЕсли
#If ExternalConnection Then
    EnglishMask = EnglishMask + 256;
#EndIf
#Если ВнешнееСоединение Тогда
    RussianMask = RussianMask + 256;
#КонецЕсли
    Return PPEncode(EnglishMask) + PPEncode(RussianMask);
EndFunction

&AtClientAtServerNoContext
Function PPDual()
    Var EnglishMask, RussianMask;
    EnglishMask = 0;
    RussianMask = 0;
#If Client Then
    EnglishMask = EnglishMask + 1;
#EndIf
#Если Клиент Тогда
    RussianMask = RussianMask + 1;
#КонецЕсли
#If Server Then
    EnglishMask = EnglishMask + 2;
#EndIf
#Если Сервер Тогда
    RussianMask = RussianMask + 2;
#КонецЕсли
#If AtClient Then
    EnglishMask = EnglishMask + 4;
#EndIf
#Если НаКлиенте Тогда
    RussianMask = RussianMask + 4;
#КонецЕсли
#If AtServer Then
    EnglishMask = EnglishMask + 8;
#EndIf
#Если НаСервере Тогда
    RussianMask = RussianMask + 8;
#КонецЕсли
#If ThinClient Then
    EnglishMask = EnglishMask + 16;
#EndIf
#Если ТонкийКлиент Тогда
    RussianMask = RussianMask + 16;
#КонецЕсли
#If WebClient Then
    EnglishMask = EnglishMask + 32;
#EndIf
#Если ВебКлиент Тогда
    RussianMask = RussianMask + 32;
#КонецЕсли
#If ThickClientOrdinaryApplication Then
    EnglishMask = EnglishMask + 64;
#EndIf
#Если ТолстыйКлиентОбычноеПриложение Тогда
    RussianMask = RussianMask + 64;
#КонецЕсли
#If ThickClientManagedApplication Then
    EnglishMask = EnglishMask + 128;
#EndIf
#Если ТолстыйКлиентУправляемоеПриложение Тогда
    RussianMask = RussianMask + 128;
#КонецЕсли
#If ExternalConnection Then
    EnglishMask = EnglishMask + 256;
#EndIf
#Если ВнешнееСоединение Тогда
    RussianMask = RussianMask + 256;
#КонецЕсли
    Return PPEncode(EnglishMask) + PPEncode(RussianMask);
EndFunction

&AtClientAtServerNoContext
Function PPEncode(Val Mask)
    Var Digits, Hundreds, Tens, Units;
    If TypeOf(Mask) <> Type("Number") Then Raise "pp-invalid-type"; EndIf;
    If Mask < 0 Or Mask > 511 Or Int(Mask) <> Mask Then Raise "pp-invalid-mask"; EndIf;
    Digits = "0123456789";
    Hundreds = Int(Mask / 100);
    Tens = Int(Mask / 10) - Hundreds * 10;
    Units = Mask - Int(Mask / 10) * 10;
    Return Mid(Digits, Hundreds + 1, 1) + Mid(Digits, Tens + 1, 1)
        + Mid(Digits, Units + 1, 1);
EndFunction

&AtServer
Function PPServerDual()
    Return PPDual();
EndFunction

&AtClient
Procedure PPAppend(RecordsOut)
    Var Encoded;
    Encoded = "pp.v1:" + PPClient() + PPServer() + PPServerNoContext()
        + PPDual() + PPServerDual();
    If StrLen(Encoded) <> 36 Then Raise "pp-invalid-token"; EndIf;
    RecordsOut.Add(Encoded);
EndProcedure
// END bounded preprocessor profile observation
