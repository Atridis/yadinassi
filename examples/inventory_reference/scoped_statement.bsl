// Read-only: use the fresh period_seed.bsl example database.
Function N(Val Value)
    Return Format(Value,"NG=0;NDS=.;NZ=0");
EndFunction
Product=Catalogs.Products.FindByCode("PS-STOCK");
Warehouse=Catalogs.Warehouses.FindByCode("PS-W");
If Product.IsEmpty() Or Warehouse.IsEmpty() Then
    Raise "Create the period stock example first";
EndIf;
Q=New Query("SELECT QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At,Product=&Product AND Warehouse=&Warehouse);
|SELECT Period AS Bucket,QuantityTurnover AS Quantity FROM AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,Month,Product=&Product AND Warehouse=&Warehouse) ORDER BY Bucket;
|SELECT Period AS Bucket,QuantityOpeningBalance AS Opening,QuantityReceipt AS Receipt,QuantityExpense AS Expense,QuantityClosingBalance AS Closing FROM AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt,Month,,Product=&Product AND Warehouse=&Warehouse) ORDER BY Bucket");
Q.SetParameter("Product",Product); Q.SetParameter("Warehouse",Warehouse);
Q.SetParameter("At",Date(2024,4,1));
Q.SetParameter("StartAt",Date(2024,1,1)); Q.SetParameter("EndAt",Date(2024,3,31,23,59,59));
// The three statements share one actual package read view.
Reports=Q.ExecuteBatch();
Rows=Reports[0].Select();
While Rows.Next() Do Message("Balance: "+N(Rows.Quantity)); EndDo;
Rows=Reports[1].Select();
While Rows.Next() Do Message("Turnover "+Format(Rows.Bucket,"DF=yyyyMM")+": "+N(Rows.Quantity)); EndDo;
Rows=Reports[2].Select();
While Rows.Next() Do
    Message("Statement "+Format(Rows.Bucket,"DF=yyyyMM")+": "+N(Rows.Opening)+","+N(Rows.Receipt)+","+N(Rows.Expense)+","+N(Rows.Closing));
EndDo;
