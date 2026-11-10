// Requires an admitted Orders document with Amount in its Lines section.
Q = New Query(
"SELECT D.Number, ISNULL(L.Total, 0) AS Total
|FROM Document.Orders AS D
|LEFT JOIN
| (SELECT Ref AS Owner, SUM(Amount) AS Total
|  FROM Document.Orders.Lines GROUP BY Ref) AS L
|ON D.Ref = L.Owner
|ORDER BY D.Number");
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Number);
    Message(Rows.Total);
EndDo;
