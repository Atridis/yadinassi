&AtServer
Procedure Create(Cancel, StandardProcessing)
    ThisObject.Title = "Create a product";
    For Each A In GetAttributes() Do
        If A.Name <> "Dirty" And A.Name <> "Saved" Then
            F = Items.Add("Field" + A.Name, Type("FormField"));
            F.Title = A.Title;
            If A.Name = "Status" Or A.Name = "Total" Then
                F.Type = FormFieldType.LabelField;
                F.ReadOnly = True;
            Else
                F.SetAction("OnChange", "Changed");
            EndIf;
            F.DataPath = A.Name;
        EndIf;
    EndDo;
    C = Commands.Add("Run"); C.Action = "RunCommand";
    B = Items.Add("RunButton", Type("FormButton"));
    B.CommandName = "Run"; B.Title = "Create product";
EndProcedure
&AtServer
Procedure Run()
    If ThisObject.Saved Then Return; EndIf;
    If ThisObject.Code = "" Or ThisObject.Description = "" Then
        Raise "Code and description are required";
    EndIf;
    P = Catalogs.Products.CreateItem();
    P.Code = ThisObject.Code;
    P.Description = ThisObject.Description;
    P.Amount = ThisObject.Amount;
    P.Write();
    ThisObject.Saved = True;
    ThisObject.Status = "Product saved";
    Items.FieldCode.ReadOnly = True;
    Items.FieldDescription.ReadOnly = True;
    Items.FieldAmount.ReadOnly = True;
    Items.RunButton.Enabled = False;
EndProcedure
