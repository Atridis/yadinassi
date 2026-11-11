&AtClient
Procedure BuildSummaryClick(Command)
    BuildSummaryAtServer();
EndProcedure
&AtServer
Procedure BuildSummaryAtServer()
    Summary = FirstName + " " + LastName + ": " + Notes;
EndProcedure
&AtClient
Procedure ToggleNamesClick(Command)
    Items.Names.ReadOnly = Not Items.Names.ReadOnly;
EndProcedure
&AtClient
Procedure ToggleNotesClick(Command)
    Items.NotesPage.Visible = Not Items.NotesPage.Visible;
EndProcedure
