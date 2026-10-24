// BEGIN bounded infobase context measurement
// Only ordinary /tmp/onec-smoke/db, verified by the native host.
// Zero-argument calls are direct; arity rejection is dynamic, not static.
&AtClient
Function IBCClient()
    Var Profile, EnglishValue, RussianValue;
    Profile = 0;
#If AtClient Then
    Profile = Profile + 1;
#EndIf
#If AtServer Then
    Profile = Profile + 2;
#EndIf
    Try
        EnglishValue = InfoBaseConnectionString();
        RussianValue = СтрокаСоединенияИнформационнойБазы();
    Except
        Return IBCEncode(Profile, 1, 0, 0, 0, 0);
    EndTry;
    Return IBCObserve(Profile, EnglishValue, RussianValue);
EndFunction

&AtServer
Function IBCServer()
    Var Profile, EnglishValue, RussianValue;
    Profile = 0;
#If AtClient Then
    Profile = Profile + 1;
#EndIf
#If AtServer Then
    Profile = Profile + 2;
#EndIf
    Try
        EnglishValue = InfoBaseConnectionString();
        RussianValue = СтрокаСоединенияИнформационнойБазы();
    Except
        Return IBCEncode(Profile, 1, 0, 0, 0, 0);
    EndTry;
    Return IBCObserve(Profile, EnglishValue, RussianValue);
EndFunction

&AtServerNoContext
Function IBCNoContext()
    Var Profile, EnglishValue, RussianValue;
    Profile = 0;
#If AtClient Then
    Profile = Profile + 1;
#EndIf
#If AtServer Then
    Profile = Profile + 2;
#EndIf
    Try
        EnglishValue = InfoBaseConnectionString();
        RussianValue = СтрокаСоединенияИнформационнойБазы();
    Except
        Return IBCEncode(Profile, 1, 0, 0, 0, 0);
    EndTry;
    Return IBCObserve(Profile, EnglishValue, RussianValue);
EndFunction

&AtClientAtServerNoContext
Function IBCDual()
    Var Profile, EnglishValue, RussianValue;
    Profile = 0;
#If AtClient Then
    Profile = Profile + 1;
#EndIf
#If AtServer Then
    Profile = Profile + 2;
#EndIf
    Try
        EnglishValue = InfoBaseConnectionString();
        RussianValue = СтрокаСоединенияИнформационнойБазы();
    Except
        Return IBCEncode(Profile, 1, 0, 0, 0, 0);
    EndTry;
    Return IBCObserve(Profile, EnglishValue, RussianValue);
EndFunction

&AtClientAtServerNoContext
Function IBCObserve(Val Profile, Val EnglishValue, Val RussianValue)
    Var Shape, Aliases, EnglishArity, RussianArity, IBCArityTemporary;
    If TypeOf(EnglishValue) <> Type("String") Or TypeOf(RussianValue) <> Type("String") Then
        Return IBCEncode(Profile, 3, 0, 0, 0, 0);
    EndIf;
    Shape = 0;
    If EnglishValue = "File=""/tmp/onec-smoke/db"";" Then Shape = 1; EndIf;
    If EnglishValue = "File=""/tmp/onec-smoke/db""" Then Shape = 2; EndIf;
    Aliases = 0;
    If EnglishValue = RussianValue Then Aliases = 1; EndIf;
    // Arity runs in this dual no-context observer, on the same side.
    // It does not measure the originating routine's arity profile.
    EnglishArity = 1;
    Try
        Execute("IBCArityTemporary = InfoBaseConnectionString(1);");
    Except
        EnglishArity = 2;
    EndTry;
    RussianArity = 1;
    Try
        Execute("IBCArityTemporary = СтрокаСоединенияИнформационнойБазы(1);");
    Except
        RussianArity = 2;
    EndTry;
    Return IBCEncode(Profile, 2, Shape, Aliases, EnglishArity, RussianArity);
EndFunction

&AtClientAtServerNoContext
Function IBCEncode(Val Profile, Val Status, Val Shape, Val Aliases, Val EnglishArity, Val RussianArity)
    Return Mid("0123", Profile + 1, 1) + Mid("0123", Status + 1, 1)
        + Mid("012", Shape + 1, 1) + Mid("01", Aliases + 1, 1)
        + Mid("012", EnglishArity + 1, 1) + Mid("012", RussianArity + 1, 1);
EndFunction

&AtServer
Function IBCServerDual()
    Return IBCDual();
EndFunction

&AtClient
Procedure IBCAppend(RecordsOut)
    Var Encoded;
    Encoded = "ibc.v1:" + IBCClient() + IBCServer() + IBCNoContext()
        + IBCDual() + IBCServerDual();
    If StrLen(Encoded) <> 37 Then Raise "ibc-invalid-token"; EndIf;
    RecordsOut.Add(Encoded);
EndProcedure
// END bounded infobase context measurement
