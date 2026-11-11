Query = New Query("SELECT P.Code AS Product,W.Code AS Warehouse,B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B INNER JOIN Catalog.Products AS P ON B.Product=P.Ref INNER JOIN Catalog.Warehouses AS W ON B.Warehouse=W.Ref");
Query.SetParameter("At", Date(2024,1,2));
Rows = Query.Execute().Select();
While Rows.Next() Do Message(Rows.Product + ", " + Rows.Warehouse + ", " + Rows.Quantity); EndDo;
Query = New Query("SELECT P.Code AS Product,W.Code AS Warehouse,T.QuantityReceipt AS Receipt,T.QuantityExpense AS Expense,T.QuantityTurnover AS Net FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt) AS T INNER JOIN Catalog.Products AS P ON T.Product=P.Ref INNER JOIN Catalog.Warehouses AS W ON T.Warehouse=W.Ref");
Query.SetParameter("StartAt", Date(2024,1,1)); Query.SetParameter("EndAt", Date(2024,1,2));
Rows = Query.Execute().Select();
While Rows.Next() Do Message("Turnovers: " + Rows.Product + ", " + Rows.Warehouse + ", receipt " + Rows.Receipt + ", expense " + Rows.Expense + ", net " + Rows.Net); EndDo;
