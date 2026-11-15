// Run once in a fresh main demo database (examples/demo).
Function Product(Val Code, Val Description, Val Kind, Val Warehouse)
    Item = Catalogs.Номенклатура.CreateItem(); Item.Code = Code;
    Item.Description = Description; Item.ВидНоменклатуры = Kind.Ref;
    SectionRow = Item.Склады.Add(); SectionRow.Склад = Warehouse.Ref;
    Item.Write(); Return Item.Ref;
EndFunction
Function Receipt(Val Number, Val At, Val Product, Val Warehouse, Val Quantity)
    Doc = Documents.Receipt.CreateDocument(); Doc.Number = Number; Doc.Date = At;
    Doc.Warehouse = Warehouse; Row = Doc.Lines.Add(); Row.Product = Product;
    Row.Quantity = Quantity; Row.Amount = Quantity * 10;
    Doc.Write(DocumentWriteMode.Posting); Return Doc.Ref;
EndFunction
Function Issue(Val Number, Val At, Val Product, Val Warehouse, Val Quantity)
    Doc = Documents.Issue.CreateDocument(); Doc.Number = Number; Doc.Date = At;
    Doc.Warehouse = Warehouse; Row = Doc.Lines.Add(); Row.Product = Product;
    Row.Quantity = Quantity; Row.Amount = Quantity * 10;
    Doc.Write(DocumentWriteMode.Posting); Return Doc.Ref;
EndFunction
Kind = Catalogs.ВидыНоменклатуры.CreateItem(); Kind.Description="Товары"; Kind.Write();
Warehouse = Catalogs.Склады.CreateItem(); Warehouse.Code = "PS-W";
Warehouse.Description = "Statement warehouse"; Warehouse.Write();
Stock = Product("PS-STOCK", "Notebook", Kind, Warehouse);
Carry = Product("PS-CARRY", "Opening stock only", Kind, Warehouse);
Balanced = Product("PS-ZERO", "Balanced movements", Kind, Warehouse);
Receipt("PS-R0", Date(2023,12,31), Stock, Warehouse.Ref, 5);
Receipt("PS-RC", Date(2023,12,31), Carry, Warehouse.Ref, 7);
Receipt("PS-R1", Date(2024,1,15), Stock, Warehouse.Ref, 10);
Issue("PS-I1", Date(2024,1,20), Stock, Warehouse.Ref, 3);
Issue("PS-I2", Date(2024,3,2), Stock, Warehouse.Ref, 2);
Receipt("PS-RZ", Date(2024,2,15), Balanced, Warehouse.Ref, 2);
Issue("PS-IZ", Date(2024,2,16), Balanced, Warehouse.Ref, 2);
Message("Stock period example created.");
