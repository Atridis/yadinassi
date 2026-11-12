Function InfoText() Export
 Return DemoService.ApplicationTitle() + ": справочники, документы и складские отчёты.";
EndFunction
Procedure OpenOperation() Export
 OpenForm("CommonForm.OperationDraft");
EndProcedure
