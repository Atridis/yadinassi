// Read-only report over receipts in the single examples/demo configuration.
// Saved, non-deleted receipts with lines, grouped by warehouse. No data is created.
// Host contract only: not evidence of native 1C query compatibility.
Query = New Query;
Query.Text = "SELECT Ref, SUM(Amount) AS Total INTO LineTotals FROM Document.Receipt.Lines GROUP BY Ref; "
    + "SELECT C.Description AS Warehouse, COUNT(*) AS Receipts, SUM(L.Total) AS Amount "
    + "FROM Document.Receipt AS D JOIN Catalog.Склады AS C ON D.Warehouse=C.Ref "
    + "JOIN LineTotals AS L ON D.Ref=L.Ref "
    + "WHERE D.DeletionMark=FALSE GROUP BY C.Description ORDER BY Warehouse";
Selection = Query.Execute().Select();
While Selection.Next() Do
    Message(Selection.Warehouse);
    Message(Selection.Receipts);
    Message(Selection.Amount);
EndDo;
