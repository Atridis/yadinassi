// Read-only Receipt lines in examples/demo: selected document states and bounded amount.
// Change the enum list to select other states. This script does not change records.
States = New Array;
States.Add(Enums.States.Draft);
Q = New Query("SELECT D.Number,L.Amount FROM Document.Receipt AS D
|JOIN Document.Receipt.Lines AS L ON D.Ref=L.Ref
|JOIN Catalog.Номенклатура AS P ON L.Product=P.Ref
|WHERE L.Amount BETWEEN 10 AND 100 AND D.State IN (&States) AND P.DeletionMark=FALSE
|ORDER BY D.Number");
Q.SetParameter("States", States);
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Number);
    Message(Rows.Amount);
EndDo;
