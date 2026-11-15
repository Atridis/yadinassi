// Requires the explicit Day-periodic Prices fixture from periodic register tests.
For I = 1 To 3 Do
    R = InformationRegisters.Prices.CreateRecordManager();
    R.Period = Date(2024, 1, I, 12, 0, 0);
    R.Item = "A";
    R.Region = "North";
    R.Price = I * 10;
    R.Enabled = I <> 2;
    R.Write();
EndDo;
Key = New Structure("Item,Region", "A", "North");
Message(InformationRegisters.Prices.GetLast(Date(2024, 1, 2), Key).Price);
Q = New Query("SELECT Item, Period, Price FROM InformationRegister.Prices.SliceLast(&At) WHERE Enabled=TRUE");
Q.SetParameter("At", Date(2024, 1, 2));
Message(Q.Execute().Unload().Count()); // 0: WHERE filters the selected latest row.

// Explicit condition is applied before selecting the last row.
Q.Text = "SELECT Item, Price FROM InformationRegister.Prices.SliceLast(&At, Enabled=&Enabled)";
Q.SetParameter("Enabled", True);
Selected = Q.Execute().Unload();
Message(Selected.Count()); // 1
Message(Selected[0].Price); // 10: Jan 1 is the last enabled row at Jan 2.
