// Fixed public scalar form oracle. No DB/file/network operations.
// Direct handler calls below are NOT automatic UI event evidence.
&AtServer
Procedure FormCreate(Cancel, StandardProcessing)
 A = New Array;
 A.Add(New FormAttribute("FName",New TypeDescription("String")));
 A.Add(New FormAttribute("FFlag",New TypeDescription("Boolean")));
 A.Add(New FormAttribute("FAmount",New TypeDescription("Number")));
 A.Add(New FormAttribute("FTrace",New TypeDescription("String")));
 A.Add(New FormAttribute("FLog",New TypeDescription("String")));
 ChangeAttributes(A);
 ThisObject.FTrace = "server-create";
 F = Items.Add("NameField",Type("FormField"));
 F.Type = FormFieldType.InputField;
 F.DataPath = "FName";
 F.SetAction("OnChange","FieldChanged");
 C = Commands.Add("Apply"); C.Action = "ApplyCommand";
 B = Items.Add("ApplyButton",Type("FormButton")); B.CommandName = "Apply";
 For N = 1 To 24 Do
  Try V = ServerCase(N); Except V = "!E"; EndTry;
  ThisObject.FLog = ThisObject.FLog + "MF" + String(N) + "=" + V + "|";
 EndDo;
EndProcedure
&AtServer
Function ServerCase(N)
 F = Items.NameField; C = Commands.Apply; B = Items.ApplyButton;
 If N=1 Then Return ?(TypeOf(ThisObject)=Type("ClientApplicationForm"),"yes","no"); EndIf;
 If N=2 Then Return F.Name; EndIf;
 If N=3 Then Return F.DataPath; EndIf;
 If N=4 Then Return C.Name; EndIf;
 If N=5 Then Return C.Action; EndIf;
 If N=6 Then Return B.CommandName; EndIf;
 If N=7 Then Return F.GetAction("OnChange"); EndIf;
 If N=8 Then Return ?(F.Type=FormFieldType.InputField,"yes","no"); EndIf;
 If N=9 Then Return ?(F.Visible,"yes","no"); EndIf;
 If N=10 Then Return ?(F.Enabled,"yes","no"); EndIf;
 If N=11 Then Return ?(F.ReadOnly,"yes","no"); EndIf;
 If N=12 Then Return ?(ThisObject.FName="","yes","no"); EndIf;
 If N=13 Then Return ?(ThisObject.FFlag=False,"yes","no"); EndIf;
 If N=14 Then Return String(ThisObject.FAmount); EndIf;
 If N=15 Then ThisObject.FName="Ada"; Return ThisObject.FName; EndIf;
 If N=16 Then ThisObject.FAmount=42; Return String(ThisObject.FAmount); EndIf;
 If N=17 Then ThisObject.FFlag=True; Return ?(ThisObject.FFlag,"yes","no"); EndIf;
 If N=18 Then F.Title="Name"; Return F.Title; EndIf;
 If N=19 Then C.Title="Apply"; Return C.Title; EndIf;
 If N=20 Then Return ?(Items.Find("NameField")=F,"yes","no"); EndIf;
 If N=21 Then Return ?(Commands.Find("Apply")=C,"yes","no"); EndIf;
 If N=22 Then
  A=New Array; A.Add(New FormAttribute("Temporary",New TypeDescription("String")));
  ChangeAttributes(A); ThisObject.Temporary="temp"; Return ThisObject.Temporary;
 EndIf;
 If N=23 Then
  D=New Array; D.Add("Temporary"); ChangeAttributes(New Array,D);
  Return "removed";
 EndIf;
 If N=24 Then Return ThisObject.FTrace; EndIf;
 Return "!E";
EndFunction
&AtClient
Procedure FormOpen(Cancel)
 ThisObject.FTrace=ThisObject.FTrace+":client-open";
 For N=25 To 40 Do
  Try V=ClientCase(N); Except V="!E"; EndTry;
  ThisObject.FLog=ThisObject.FLog+"MF"+String(N)+"="+V+"|";
 EndDo;
 // The reviewed route must capture this bounded fixed record, not raw errors.
 Message(ThisObject.FLog);
EndProcedure
&AtClient
Function ClientCase(N)
 If N=25 Then Return ThisObject.FTrace; EndIf;
 If N=26 Then Return ServerRead(); EndIf;
 If N=27 Then ServerSet(); Return ThisObject.FName; EndIf;
 If N=28 Then Items.NameField.Title="ClientName"; Return Items.NameField.Title; EndIf;
 If N=29 Then ThisObject.FName="programmatic"; Return ThisObject.FTrace; EndIf;
 If N=30 Then Return ThisObject.FName; EndIf;
 If N=31 Then FieldChanged(Items.NameField); Return ThisObject.FTrace; EndIf;
 If N=32 Then Return ThisObject.FName; EndIf;
 If N=33 Then ApplyCommand(Commands.Apply); Return ThisObject.FTrace; EndIf;
 If N=34 Then Return String(ThisObject.FAmount); EndIf;
 If N=35 Then ThisObject.FFlag=False; Return ?(ServerFlag(),"yes","no"); EndIf;
 If N=36 Then ThisObject.FName="stay"; Return ThisObject.FName; EndIf;
 If N=37 Then
  C=False; E=False; M=""; S=True; FormBeforeClose(C,E,M,S);
  Return ?(C,"cancel","continue");
 EndIf;
 If N=38 Then ThisObject.FName="leave"; Return ThisObject.FName; EndIf;
 If N=39 Then
  C=False; E=False; M=""; S=True; FormBeforeClose(C,E,M,S);
  Return ?(C,"cancel","continue");
 EndIf;
 If N=40 Then Return "direct-calls-complete"; EndIf;
 Return "!E";
EndFunction
&AtServer
Function ServerRead()
 Return ThisObject.FName;
EndFunction
&AtServer
Procedure ServerSet()
 ThisObject.FName="server-updated";
EndProcedure
&AtServer
Function ServerFlag()
 Return ThisObject.FFlag;
EndFunction
&AtClient
Procedure FieldChanged(Item)
 ThisObject.FTrace="direct-change:"+Item.Name;
 ThisObject.FName="handler-change";
EndProcedure
&AtClient
Procedure ApplyCommand(Command)
 ThisObject.FTrace="direct-command:"+Command.Name;
 ThisObject.FAmount=ThisObject.FAmount+1;
EndProcedure
&AtClient
Procedure FormBeforeClose(Cancel,Exit,MessageText,StandardProcessing)
 Cancel=ThisObject.FName="stay";
EndProcedure
