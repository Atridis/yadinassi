&AtServer
Procedure Create(Cancel, StandardProcessing)
    ThisObject.Title = "Choose a catalog record";
    F = Items.Add("FieldSearchCode", Type("FormField"));
    F.Title = "Find exact code (empty shows first 32)";
    F.DataPath = "SearchCode";
    F = Items.Add("FieldStatus", Type("FormField"));
    F.Type = FormFieldType.LabelField;
    F.ReadOnly = True;
    F.DataPath = "Status";
    T = Items.Add("ChoicesTable", Type("FormTable"));
    T.DataPath = "Choices";
    T.ReadOnly = True;
    AddButton("SearchChoices", "SearchCommand", "Find records");
    AddButton("Choose", "ChooseCommand", "Choose selected record");
    AddButton("Cancel", "CancelCommand", "Cancel selection");
    ChoiceSearch();
EndProcedure

&AtServer
Procedure AddButton(Val Name, Val Handler, Val Caption)
    C = Commands.Add(Name);
    C.Action = Handler;
    B = Items.Add(Name + "Button", Type("FormButton"));
    B.CommandName = Name;
    B.Title = Caption;
EndProcedure

&AtServer
Procedure SearchChoices()
    ChoiceSearch();
EndProcedure

&AtServer
Procedure Choose()
    ChoiceSelect();
EndProcedure

&AtServer
Procedure CancelChoice()
    ChoiceCancel();
EndProcedure
