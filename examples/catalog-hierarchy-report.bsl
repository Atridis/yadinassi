// Requires Products admitted with HierarchyFoldersAndItems.
Group = Catalogs.Products.CreateFolder();
Group.Code = "TOOLS";
Group.Description = "Tools";
Group.Write();
Item = Catalogs.Products.CreateItem();
Item.Code = "HAMMER";
Item.Description = "Hammer";
Item.Parent = Group.Ref;
Item.Write();
Report = New Query("SELECT Code, Description, Parent, IsFolder
|FROM Catalog.Products
|WHERE Ref IN HIERARCHY (&Root)
|ORDER BY Code");
Report.SetParameter("Root", Group.Ref);
Rows = Report.Execute().Select();
While Rows.Next() Do
    Message(Rows.Code + ": " + Rows.Description);
EndDo;
