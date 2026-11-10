// Requires an activated local Prices register with Item/Region dimensions,
// Price resource and Enabled attribute, as described in the register profile.
Prices = InformationRegisters.Prices.CreateRecordSet();
Prices.Filter.Region.Set("North");
Row = Prices.Add();
Row.Item = "A";
Row.Price = 12.50;
Row.Enabled = True;
Row = Prices.Add();
Row.Item = "B";
Row.Price = 19;
Row.Enabled = True;
Prices.Write();
Selection = InformationRegisters.Prices.Select(New Structure("Region", "North"));
While Selection.Next() Do
    Message(Selection.Item + ": " + String(Selection.Price));
EndDo;
