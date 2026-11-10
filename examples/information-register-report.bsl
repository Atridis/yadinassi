// Read-only host report. Requires independent nonperiodic Rates with
// Category (Catalog.Categories), Amount and Enabled fields.
Q = New Query;
Q.Text = "SELECT Category,SUM(Amount) AS Total INTO Totals FROM InformationRegister.Rates WHERE Enabled=TRUE GROUP BY Category; "
    + "SELECT C.Description AS Category,T.Total FROM Totals AS T JOIN Catalog.Categories AS C ON T.Category=C.Ref ORDER BY Category";
S = Q.Execute().Select();
While S.Next() Do
    Message(S.Category);
    Message(S.Total);
EndDo;
