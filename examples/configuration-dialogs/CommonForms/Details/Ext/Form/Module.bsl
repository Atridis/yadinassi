&AtServer
Procedure Created(Cancel, StandardProcessing)
 If Parameters.Property("Message") Then MessageText = Parameters.Message; EndIf;
EndProcedure
&AtClient
Procedure AcceptResult(Command)
 Close(New Structure("Text", MessageText));
EndProcedure

&AtClient
Procedure Closing(Cancel, Quitting, Warning, StandardProcessing)
 If KeepOpen Then
  Cancel = True;
  Message("Uncheck Keep chooser open before closing");
 EndIf;
EndProcedure
