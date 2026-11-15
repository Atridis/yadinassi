// Run once in a fresh database; all identifiers below are owned demo data.
Kind = Catalogs.ВидыНоменклатуры.CreateItem(); Kind.Description = "Товары"; Kind.Write();
W = Catalogs.Склады.CreateItem(); W.Code = "W1"; W.Description = "Main warehouse"; W.Write();
P = Catalogs.Номенклатура.CreateItem(); P.Code = "P1"; P.Description = "Notebook";
P.ВидНоменклатуры = Kind.Ref; SectionRow = P.Склады.Add(); SectionRow.Склад = W.Ref; P.Write();
Receipt = Documents.Receipt.CreateDocument(); Receipt.Number = "R1"; Receipt.Date = Date(2024,1,1,12,0,0);
Receipt.Warehouse = W.Ref;
Line = Receipt.Lines.Add(); Line.Product = P.Ref; Line.Quantity = 10; Line.Amount = 100;
Receipt.Write(DocumentWriteMode.Posting);
Issue = Documents.Issue.CreateDocument(); Issue.Number = "I1"; Issue.Date = Date(2024,1,1,13,0,0);
Issue.Warehouse = W.Ref;
Line = Issue.Lines.Add(); Line.Product = P.Ref; Line.Quantity = 3; Line.Amount = 30;
Issue.Write(DocumentWriteMode.Posting);

Query = New Query("SELECT P.Description AS Product,W.Description AS Warehouse,B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B INNER JOIN Catalog.Номенклатура AS P ON B.Product=P.Ref INNER JOIN Catalog.Склады AS W ON B.Warehouse=W.Ref");
Query.SetParameter("At", Date(2024,1,2));
Rows = Query.Execute().Select(); Rows.Next();
Message("After issue: " + Rows.Product + ", " + Rows.Warehouse + ", " + Rows.Quantity);

Rejected = Documents.Issue.CreateDocument(); Rejected.Number = "I2"; Rejected.Date = Date(2024,1,1,14,0,0);
Rejected.Warehouse = W.Ref; Line = Rejected.Lines.Add(); Line.Product = P.Ref; Line.Quantity = 100; Line.Amount = 1000;
Failed = False;
Try Rejected.Write(DocumentWriteMode.Posting); Except Failed = True; EndTry;
If Not Failed Then Raise "The authored stock rule failed"; EndIf;
Rows = Query.Execute().Select(); Rows.Next(); Message("After refused issue: " + Rows.Quantity);

Issue.Write(DocumentWriteMode.UndoPosting);
Rows = Query.Execute().Select(); Rows.Next(); Message("After unpost: " + Rows.Quantity);
Issue = Issue.Ref.GetObject(); Issue.Lines[0].Quantity = 2; Issue.Lines[0].Amount = 20;
Issue.Write(DocumentWriteMode.Posting);
Rows = Query.Execute().Select(); Rows.Next(); Message("After repost: " + Rows.Quantity);
