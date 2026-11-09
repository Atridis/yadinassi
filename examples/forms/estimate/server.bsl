&AtServer
Procedure Create(Cancel, StandardProcessing)
    ThisObject.Title = "Estimate calculator";
    For Each A In GetAttributes() Do
        If A.Name <> "Dirty" And A.Name <> "Saved" Then
            F = Items.Add("Field" + A.Name, Type("FormField"));
            F.Title = A.Title;
            F.DataPath = A.Name;
            If A.Name = "Status" Or A.Name = "Total" Then
                F.Type = FormFieldType.LabelField;
                F.ReadOnly = True;
            Else
                F.SetAction("OnChange", "Changed");
            EndIf;
        EndIf;
    EndDo;
    C = Commands.Add("Run"); C.Action = "RunCommand";
    B = Items.Add("RunButton", Type("FormButton"));
    B.CommandName = "Run"; B.Title = "Calculate";
EndProcedure
&AtServer
Procedure Run()
    ThisObject.Total = ThisObject.Price * ThisObject.Quantity;
    ThisObject.Status = "Calculated on the server";
EndProcedure
