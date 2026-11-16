rows=New Array;totals=New Map;
For i=1 To 1000 Do
    category=i%2;row=New Structure("category,quantity,price",category,i,10+i);rows.Add(row);
EndDo;
result=0;trace=0;
For Each row In rows Do
    Observe(row.category);amount=row.quantity*row.price;result=result+amount;
    previous=totals.Get(row.category);If previous=Undefined Then previous=0;EndIf;
    totals.Insert(row.category,previous+amount);trace=(trace*10+row.category)%1000003;
EndDo;
evenTotal=totals.Get(0);oddTotal=totals.Get(1);
first=rows[0];alias=first;alias.quantity=alias.quantity+10;
aliasQuantity=rows[0].quantity;rowCount=rows.Count();
