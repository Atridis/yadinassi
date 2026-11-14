// Run once in the main examples/demo database; no separate enum configuration.
Kind=Catalogs.ВидыНоменклатуры.CreateItem(); Kind.Description="Товары"; Kind.Write();
W=Catalogs.Склады.CreateItem(); W.Code="ER-W"; W.Description="Enum warehouse"; W.Write();
P=Catalogs.Номенклатура.CreateItem(); P.Code="ER-P"; P.Description="Enum product";
P.ВидНоменклатуры=Kind.Ref; SectionRow=P.Склады.Add(); SectionRow.Склад=W.Ref; P.Write();
D=Documents.Receipt.CreateDocument(); D.Number="ER-POST"; D.Date=Date(2024,2,1);
D.Warehouse=W.Ref; D.State=Enums.States.Approved;
L=D.Lines.Add(); L.Product=P.Ref; L.Unit=Enums.Units.Piece; L.Quantity=6; L.Amount=12;
D.Write(DocumentWriteMode.Posting);
D=Documents.Receipt.CreateDocument(); D.Number="ER-PENDING"; D.Date=Date(2024,2,2);
D.Warehouse=W.Ref; D.State=Enums.States.Draft;
L=D.Lines.Add(); L.Product=P.Ref; L.Unit=Enums.Units.Piece; L.Quantity=4; L.Amount=8;
D.Write();
