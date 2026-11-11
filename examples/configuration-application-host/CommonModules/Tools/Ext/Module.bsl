Procedure ShowWelcome() Export
 OpenForm("CommonForm.Welcome");
EndProcedure

Procedure ShowDetails(Val Text) Export
 OpenForm("CommonForm.Details", New Structure("Message", Text));
EndProcedure
