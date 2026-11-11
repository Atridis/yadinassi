&AtServer
Procedure Created(Cancel, StandardProcessing)
 If Parameters.Property("Message") Then
  MessageText = Parameters.Message;
 Else
  MessageText = "Open Welcome to pass a message";
 EndIf;
EndProcedure
