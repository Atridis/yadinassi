// Read-only Receipt totals in the single examples/demo configuration.
// Includes saved drafts and posted receipts; documents without lines have total 0.
Q = New Query(
"SELECT D.Number, ISNULL(L.Total, 0) AS Total
|FROM Document.Receipt AS D
|LEFT JOIN
| (SELECT Ref AS Owner, SUM(Amount) AS Total
|  FROM Document.Receipt.Lines GROUP BY Ref) AS L
|ON D.Ref = L.Owner
|ORDER BY D.Number");
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Number);
    Message(Rows.Total);
EndDo;
