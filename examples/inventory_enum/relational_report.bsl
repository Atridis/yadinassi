// Read-only actual stock plus unposted receipts; run after seed.bsl.
W=Catalogs.Склады.FindByCode("ER-W");
If W.IsEmpty() Then Raise "Run the enum seed script in the main demo first"; EndIf;
Units=New Array; Units.Add(Enums.Units.Piece); Units.Add(Enums.Units.Pack);
Q=New Query("SELECT T.Product AS Product,T.Unit AS Unit,SUM(T.Quantity) AS Quantity
|FROM
| (SELECT P.Code AS Product,ISNULL(S.Unit,&DefaultUnit) AS Unit,ISNULL(S.QuantityBalance,0) AS Quantity
|  FROM Catalog.Номенклатура AS P
|  LEFT JOIN AccumulationRegister.Stock.Balance(&At,Warehouse=&Warehouse) AS S ON S.Product=P.Ref
|  UNION ALL
|  SELECT P.Code AS Product,L.Unit AS Unit,L.Quantity AS Quantity
|  FROM Document.Receipt.Lines AS L
|  INNER JOIN Document.Receipt AS D ON L.Ref=D.Ref
|  INNER JOIN Catalog.Номенклатура AS P ON L.Product=P.Ref
|  WHERE D.Posted=False AND D.Warehouse=&Warehouse) AS T
|WHERE T.Unit IN (&Units)
|GROUP BY T.Product,T.Unit
|ORDER BY T.Product");
Q.SetParameter("At",Date(2024,3,31,23,59,59));
Q.SetParameter("DefaultUnit",Enums.Units.Piece);
Q.SetParameter("Warehouse",W); Q.SetParameter("Units",Units);
Rows=Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Product); Message(Rows.Unit); Message(Rows.Quantity);
EndDo;
