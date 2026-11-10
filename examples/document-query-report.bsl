// Read-only report over an already populated owned SQLite document database.
// Required schema: Document.Orders with Amount, Category (Catalog.Categories),
// and Lines.Amount. Categories has Description. This script creates no data.
// The authored test fixture is tests/test_document_queries.py: report_files().
// Host contract only: not evidence of native 1C query compatibility.

Query = New Query;
Query.Text = "SELECT Ref, SUM(Amount) AS Total INTO LineTotals FROM Document.Orders.Lines GROUP BY Ref; "
    + "SELECT C.Description AS Customer, COUNT(*) AS Orders, SUM(D.Amount) AS Amount, SUM(L.Total) AS LineAmount "
    + "FROM Document.Orders AS D JOIN Catalog.Categories AS C ON D.Category=C.Ref "
    + "JOIN LineTotals AS L ON D.Ref=L.Ref "
    + "WHERE D.DeletionMark=FALSE GROUP BY C.Description ORDER BY Customer";
Selection = Query.Execute().Select();
While Selection.Next() Do
    Message(Selection.Customer);
    Message(Selection.Orders);
    Message(Selection.Amount);
    Message(Selection.LineAmount);
EndDo;
