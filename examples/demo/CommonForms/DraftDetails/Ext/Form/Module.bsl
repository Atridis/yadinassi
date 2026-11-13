&AtServer
Procedure Created(Cancel, StandardProcessing)
 If Parameters.Property("DraftTitle") Then DraftTitle = Parameters.DraftTitle; EndIf;
 If Parameters.Property("Amount") Then Amount = Parameters.Amount; EndIf;
 If Parameters.Property("Comment") Then Comment = Parameters.Comment; EndIf;
EndProcedure
&AtClient
Procedure AcceptDraft(Command)
 Close(New Structure("DraftTitle,Amount,Comment", DraftTitle, Amount, Comment));
EndProcedure
&AtClient
Procedure CancelDraft(Command)
 Close(Undefined);
EndProcedure
&AtClient
Procedure Closing(Cancel, Quitting, Warning, StandardProcessing)
 If KeepOpen Then
  Cancel = True;
  Message("Снимите флажок KeepOpen, чтобы закрыть черновик");
 EndIf;
EndProcedure
