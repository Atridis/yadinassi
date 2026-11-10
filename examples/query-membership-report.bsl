// Local typed Query example; Products and Categories must exist.
Excluded = New Array;
Excluded.Add("archived");
Q = New Query("SELECT P.Code,P.Amount FROM Catalog.Products AS P
|WHERE P.Amount BETWEEN 10 AND 100 AND P.Code NOT IN &Excluded
|AND P.Category IN (SELECT C.Ref FROM Catalog.Categories AS C WHERE NOT C.DeletionMark=TRUE)
|ORDER BY P.Code");
Q.SetParameter("Excluded", Excluded);
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Code);
    Message(Rows.Amount);
EndDo;
