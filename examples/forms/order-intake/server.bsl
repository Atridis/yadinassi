// Server activations do not retain module Var values. The object is local to SaveOrder.
&AtServer
Procedure Create(Cancel, StandardProcessing)
    ThisObject.Title = "Create an order";
    For Each A In GetAttributes() Do
        If A.Name <> "Dirty" And A.Name <> "Saved" And A.Name <> "SaveAttempted" Then
            F = Items.Add("Field" + A.Name, Type("FormField"));
            F.Title = A.Title;
            If A.Name = "Total" Or A.Name = "Status" Then
                F.Type = FormFieldType.LabelField;
                F.ReadOnly = True;
            Else
                F.SetAction("OnChange", "Changed");
            EndIf;
            F.DataPath = A.Name;
        EndIf;
    EndDo;
    T = Items.Add("LinesTable", Type("FormTable"));
    T.Title = "Order lines";
    T.DataPath = "Lines";
    T.SetAction("OnChange", "Changed");
    AddButton("AddLine", "AddCommand", "Add line");
    AddButton("DeleteLine", "DeleteCommand", "Delete selected line");
    AddButton("Recalculate", "RecalculateCommand", "Recalculate");
    AddButton("SaveOrder", "SaveCommand", "Save order");
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
    If ThisObject.SaveAttempted Then Return; EndIf;
    R = ThisObject.Lines.Add();
    R.Quantity = 1;
    Items.LinesTable.CurrentRow = R.GetID();
    ThisObject.Dirty = True;
    ThisObject.Status = "New line selected; enter its description, quantity and price";
EndProcedure

&AtServer
Procedure DeleteLine()
    If ThisObject.SaveAttempted Then Return; EndIf;
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
    If ThisObject.SaveAttempted Then Return; EndIf;
    ValidateLines();
    CalculateTotals();
    ThisObject.Status = "Totals recalculated; order is not yet saved";
EndProcedure

&AtServer
Procedure LockEditing()
    Items.FieldCode.ReadOnly = True;
    Items.FieldDescription.ReadOnly = True;
    Items.LinesTable.ReadOnly = True;
    Items.AddLineButton.Enabled = False;
    Items.DeleteLineButton.Enabled = False;
    Items.RecalculateButton.Enabled = False;
    Items.SaveOrderButton.Enabled = False;
EndProcedure

&AtServer
Procedure SaveOrder()
    If ThisObject.SaveAttempted Then Return; EndIf;
    // Recoverable user input is checked before acquiring the conservative write lock.
    If TrimAll(ThisObject.Code) = "" Or StrLen(ThisObject.Code) > 8 Then
        RejectInput("Code requires 1 to 8 characters");
    EndIf;
    If TrimAll(ThisObject.Description) = "" Or StrLen(ThisObject.Description) > 64 Then
        RejectInput("Order description requires 1 to 64 characters");
    EndIf;
    ValidateLines();
    If Not Catalogs.Orders.FindByCode(ThisObject.Code).IsEmpty() Then
        RejectInput("An order with this code already exists");
    EndIf;
    CalculateTotals();
    O = Catalogs.Orders.CreateItem();
    O.Code = ThisObject.Code;
    O.Description = ThisObject.Description;
    O.Total = ThisObject.Total;
    For Each R In ThisObject.Lines Do
        L = O.Lines.Add();
        // Stored row names reserve Description; the UI schema stays user-facing.
        L.ItemDescription = R.Description;
        L.Quantity = R.Quantity;
        L.Price = R.Price;
        L.Amount = R.Amount;
    EndDo;
    // A thrown server error is not proof of rollback. Never automatically retry Write.
    ThisObject.SaveAttempted = True;
    LockEditing();
    ThisObject.Status = "Save attempted; verify the database before starting another order";
    O.Write();
    ThisObject.Saved = True;
    ThisObject.Dirty = False;
    ThisObject.Status = "Order saved";
EndProcedure
