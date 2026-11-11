Procedure ShowWelcome() Export
 OpenForm("CommonForm.Welcome");
EndProcedure

Procedure ShowDetails(Val Text) Export
 OpenForm("CommonForm.Details", New Structure("Message", Text));
EndProcedure

Procedure NewProduct() Export
 OpenForm("Catalog.Products.Form.Card");
EndProcedure

Procedure NewCategory() Export
 OpenForm("Catalog.Categories.Form.Card");
EndProcedure

Procedure NewOrder() Export
 OpenForm("Document.Orders.Form.Card");
EndProcedure
