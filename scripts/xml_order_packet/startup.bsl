// Authored experiment driver. Only installed into disposable copied configuration.
Procedure ПриНачалеРаботыСистемы()
 AttachIdleHandler("XmlOrderStart", 1, True);
EndProcedure

Procedure XmlOrderStart() Export
 P = New Structure("DraftTitle,Amount,Comment", "XML-order witness", 17, "scope-check");
 OpenForm("CommonForm.DraftDetails", P, Undefined, True);
EndProcedure
