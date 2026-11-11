&AtServer
Procedure Create(Cancel, StandardProcessing)
    ThisObject.Title = "Order with customer and products";
    For Each A In GetAttributes() Do
        If A.Name <> "Dirty" And A.Name <> "Loaded" And A.Name <> "Locked" Then
            F = Items.Add("Field" + A.Name, Type("FormField"));
            F.Title = A.Title;
            If A.Name = "Total" Or A.Name = "Status" Or A.Name = "Customer" Then
                F.Type = FormFieldType.LabelField;
                F.ReadOnly = True;
            ElsIf A.Name <> "SearchCode" Then
                F.SetAction("OnChange", "Changed");
            EndIf;
            F.DataPath = A.Name;
        EndIf;
    EndDo;
    AddButton("ChooseCustomer", "ChooseCustomerCommand", "Choose customer");
    T = Items.Add("LinesTable", Type("FormTable"));
    T.Title = "Order lines";
    T.DataPath = "Lines";
    T.SetAction("OnChange", "Changed");
    AddButton("ChooseProduct", "ChooseProductCommand", "Choose product for selected line");
    AddButton("AddLine", "AddCommand", "Add line");
    AddButton("DeleteLine", "DeleteCommand", "Delete selected line");
    AddButton("Recalculate", "RecalculateCommand", "Recalculate");
    AddButton("SaveOrder", "SaveCommand", "Save changes");
    AddButton("Discard", "DiscardCommand", "Discard / Reload");
    AddButton("Resolve", "ResolveCommand", "Resolve save outcome");
    WorkbenchBrowse();
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
Procedure AddLine()
    If ThisObject.Locked Or Not ThisObject.Loaded Then Return; EndIf;
    R = ThisObject.Lines.Add();
    R.Quantity = 1;
    Items.LinesTable.CurrentRow = R.GetID();
    ThisObject.Dirty = True;
    ThisObject.Status = "New line selected; choose a product, then enter quantity and price";
EndProcedure

&AtServer
Procedure DeleteLine()
    If ThisObject.Locked Or Not ThisObject.Loaded Then Return; EndIf;
    R = Items.LinesTable.CurrentData;
    If R = Undefined Then
        RejectInput("Select a line to delete");
    EndIf;
    ThisObject.Lines.Delete(R);
    Items.LinesTable.CurrentRow = Undefined;
    ThisObject.Dirty = True;
    ThisObject.Status = "Line deleted; recalculate or save the order";
EndProcedure

&AtServer
Procedure RejectInput(Val Explanation)
    ThisObject.Status = Explanation;
    Raise Explanation;
EndProcedure

&AtServer
Procedure ValidateLines()
    If ThisObject.Lines.Count() = 0 Then
        RejectInput("Add at least one order line");
    EndIf;
    For Each R In ThisObject.Lines Do
        If TrimAll(R.Description) = "" Or StrLen(R.Description) > 128 Then
            RejectInput("Line descriptions require 1 to 128 characters");
        EndIf;
        If R.Quantity <= 0 Or R.Quantity > 1000000 Or R.Quantity <> Round(R.Quantity, 2) Then
            RejectInput("Quantity must be positive, at most 1000000 and have at most two decimal places");
        EndIf;
        If R.Price < 0 Or R.Price > 1000000 Or R.Price <> Round(R.Price, 2) Then
            RejectInput("Price must be nonnegative, at most 1000000 and have at most two decimal places");
        EndIf;
    EndDo;
EndProcedure

&AtServer
Procedure CalculateTotals()
    CalculatedTotal = 0;
    For Each R In ThisObject.Lines Do
        R.Amount = Round(R.Quantity * R.Price, 2);
        CalculatedTotal = CalculatedTotal + R.Amount;
    EndDo;
    ThisObject.Total = CalculatedTotal;
EndProcedure

&AtServer
Procedure Recalculate()
    If ThisObject.Locked Or Not ThisObject.Loaded Then Return; EndIf;
    ValidateLines();
    CalculateTotals();
    WorkbenchDirty();
    ThisObject.Status = "Totals recalculated; order is not yet saved";
EndProcedure

// Only these fixed host functions hold the selected detached object and revision.
// Server module Var values remain fresh on every activation.
&AtServer
Procedure ChooseCustomer()
    ReferenceChooseCustomer();
EndProcedure

&AtServer
Procedure ChooseProduct()
    ReferenceChooseProduct();
EndProcedure

&AtServer
Procedure ApplyChoice()
    ReferenceApplyChoice();
EndProcedure

&AtServer
Procedure DiscardOrder()
    WorkbenchReload();
EndProcedure

&AtServer
Procedure ResolveOrder()
    WorkbenchResolve();
EndProcedure

&AtServer
Procedure SaveOrder()
    If ThisObject.Locked Or Not ThisObject.Loaded Then Return; EndIf;
    If TrimAll(ThisObject.Code) = "" Or StrLen(ThisObject.Code) > 8 Then
        RejectInput("Code requires 1 to 8 characters");
    EndIf;
    If TrimAll(ThisObject.Description) = "" Or StrLen(ThisObject.Description) > 64 Then
        RejectInput("Order description requires 1 to 64 characters");
    EndIf;
    ValidateLines();
    CalculateTotals();
    WorkbenchSave();
EndProcedure
