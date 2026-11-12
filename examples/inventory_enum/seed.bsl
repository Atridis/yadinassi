// Fresh inventory-enum-v1 database only; intentionally no implicit migration.
P=Catalogs.Products.CreateItem(); P.Code="ER-P"; P.Unit=Enums.Units.Piece; P.Write();
W=Catalogs.Warehouses.CreateItem(); W.Code="ER-W"; W.Write();
D=Documents.Receipt.CreateDocument(); D.Number="ER-POST"; D.Date=Date(2024,2,1);
D.Warehouse=W.Ref; D.State=Enums.States.Approved;
L=D.Lines.Add(); L.Product=P.Ref; L.Unit=Enums.Units.Piece; L.Quantity=6; L.Amount=12;
D.Write(DocumentWriteMode.Posting);
D=Documents.Receipt.CreateDocument(); D.Number="ER-PENDING"; D.Date=Date(2024,2,2);
D.Warehouse=W.Ref; D.State=Enums.States.Draft;
L=D.Lines.Add(); L.Product=P.Ref; L.Unit=Enums.Units.Piece; L.Quantity=4; L.Amount=8;
D.Write();
