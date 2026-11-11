Query = New Query("SELECT P.Code AS Product,W.Code AS Warehouse,B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B INNER JOIN Catalog.Products AS P ON B.Product=P.Ref INNER JOIN Catalog.Warehouses AS W ON B.Warehouse=W.Ref");
Query.SetParameter("At", Date(2024,1,2));
Rows = Query.Execute().Select();
While Rows.Next() Do Message(Rows.Product + ", " + Rows.Warehouse + ", " + Rows.Quantity); EndDo;
