// Read-only: reopen the database after period_seed.bsl, then after reconciliation.
Query = New Query("SELECT S.Period AS Bucket,P.Code AS Product,W.Code AS Warehouse,S.QuantityOpeningBalance AS Opening,S.QuantityReceipt AS Receipt,S.QuantityExpense AS Expense,S.QuantityTurnover AS Net,S.QuantityClosingBalance AS Closing FROM AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt,Month) AS S INNER JOIN Catalog.Номенклатура AS P ON S.Product=P.Ref INNER JOIN Catalog.Склады AS W ON S.Warehouse=W.Ref ORDER BY Bucket,Product,Warehouse");
Query.SetParameter("StartAt", Date(2024,1,1));
Query.SetParameter("EndAt", Date(2024,4,30,23,59,59));
Rows = Query.Execute().Select();
Message("Month | Product | Warehouse | Opening | Receipt | Expense | Net | Closing");
While Rows.Next() Do
    Message(Format(Rows.Bucket,"DF=yyyy-MM-dd") + " | " + Rows.Product + " | " + Rows.Warehouse
        + " | " + Rows.Opening + " | " + Rows.Receipt + " | " + Rows.Expense
        + " | " + Rows.Net + " | " + Rows.Closing);
EndDo;
