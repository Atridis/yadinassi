&AtServer
Procedure Created(Cancel, StandardProcessing)
 Greeting = "Products, categories and non-posting orders in one application";
EndProcedure

&AtClient
Procedure ShowDetails(Command)
 Message(Service.Add(4));
 Tools.ShowDetails(Greeting);
EndProcedure

&AtClient
Procedure NewProduct(Command)
 Tools.NewProduct();
EndProcedure

&AtClient
Procedure NewCategory(Command)
 Tools.NewCategory();
EndProcedure

&AtClient
Procedure NewOrder(Command)
 Tools.NewOrder();
EndProcedure
