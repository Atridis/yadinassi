Function CQCodes(Result)
S=Result.Select();T="";N=0;
While S.Next() Do
N=N+1;If N>3 Then Raise "owned query row bound";EndIf;
If N>1 Then T=T+",";EndIf;T=T+S.Code;
EndDo;
Return T;
EndFunction
M=Catalogs.OwnedQuery31339d83;
P=M.CreateItem();P.SetNewObjectRef(M.GetRef(New UUID("8a1a06d0-a34e-457b-80df-1728eb2d8a7e")));
P.Code="02";P.Description="Alpha";P.Quantity=20;P.Active=False;P.Stamp=Date(2024,2,29,12,0,1);P.Write();
P=M.CreateItem();P.SetNewObjectRef(M.GetRef(New UUID("add18115-fcc5-435e-a914-8cb9db25e6ff")));
P.Code="03";P.Description="beta";P.Quantity=30;P.Active=True;P.Stamp=Date(2024,2,29,12,0,2);P.Write();
P=M.CreateItem();P.SetNewObjectRef(M.GetRef(New UUID("d8bd0051-ec79-44e4-bf94-04ffb42bd865")));
P.Code="01";P.Description="alpha";P.Quantity=10;P.Active=True;P.Stamp=Date(2024,2,29,12,0,0);P.Write();
Q=New Query("SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Description=&Name ORDER BY Quantity");Q.SetParameter("Name","alpha");CQEmit(1,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 ORDER BY Quantity";R=Q.Execute();S=R.Select();
CQEmit(2,TypeOf(R)=Type("QueryResult"));CQEmit(3,TypeOf(S)=Type("QueryResultSelection"));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Quantity=&Missing";Refused=False;Try Q.Execute();Except Refused=True;EndTry;CQEmit(4,Refused);
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Quantity>=&Min ORDER BY Quantity";Q.SetParameter("Min",20);CQEmit(5,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Active=&Flag ORDER BY Quantity";Q.SetParameter("Flag",True);CQEmit(6,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Stamp>=&Moment ORDER BY Quantity";Q.SetParameter("Moment",Date(2024,2,29,12,0,1));CQEmit(7,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Ref=&Item";Q.SetParameter("Item",M.GetRef(New UUID("d8bd0051-ec79-44e4-bf94-04ffb42bd865")));CQEmit(8,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 ORDER BY Quantity ASC";CQEmit(9,CQCodes(Q.Execute()));
Q.Text="SELECT TOP 2 Code FROM Catalog.OwnedQuery31339d83 ORDER BY Quantity DESC";CQEmit(10,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE (Quantity=10 OR Quantity=20) AND Active=TRUE ORDER BY Quantity";CQEmit(11,CQCodes(Q.Execute()));
Q.Text="ВЫБРАТЬ П.Код КАК Code ИЗ Справочник.OwnedQuery31339d83 КАК П ГДЕ П.Quantity>10 УПОРЯДОЧИТЬ ПО П.Quantity УБЫВ";CQEmit(12,CQCodes(Q.Execute()));
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 WHERE Quantity>100";Empty=Q.Execute();CQEmit(13,Empty.IsEmpty());ES=Empty.Select();CQEmit(14,ES.Next());
Q.Text="SELECT Code FROM Catalog.OwnedQuery31339d83 ORDER BY Quantity";R=Q.Execute();S=R.Select();
Probe="action-error";Try Probe=String(TypeOf(S.Code))+":"+String(S.Code);Except EndTry;BeforeProbe=Probe;
Counter=0;While S.Next() Do Counter=Counter+1;If Counter>3 Then Raise "owned query row bound";EndIf;EndDo;
CQEmit(15,S.Next());CQEmit(16,BeforeProbe);Probe="action-error";Try Probe=String(TypeOf(S.Code))+":"+String(S.Code);Except EndTry;CQEmit(17,Probe);
Q.Text="SELECT Code,Quantity,Active,Stamp FROM Catalog.OwnedQuery31339d83 ORDER BY Quantity";R=Q.Execute();T=R.Unload();CQEmit(18,TypeOf(T)=Type("ValueTable"));CQEmit(19,T.Count());
CQEmit(20,T.Columns[0].Name+"/"+T.Columns[1].Name+"/"+T.Columns[2].Name+"/"+T.Columns[3].Name);
CQEmit(21,String(T.Columns[0].ValueType)+"/"+String(T.Columns[1].ValueType)+"/"+String(T.Columns[2].ValueType)+"/"+String(T.Columns[3].ValueType));
CQEmit(22,String(T.Columns[0].ValueType.StringQualifiers.Length)+"/"+String(T.Columns[1].ValueType.NumberQualifiers.Digits)+"/"+String(T.Columns[1].ValueType.NumberQualifiers.FractionDigits)+"/"+String(T.Columns[3].ValueType.DateQualifiers.DateFractions));
T[0].Quantity=999;S=R.Select();S.Next();CQEmit(23,String(S.Quantity)+"/"+String(M.FindByCode("01").Quantity));
A=R.Select();B=R.Select();A.Next();A.Next();B.Next();Q.SetParameter("Min",100);
CQEmit(24,A.Code="02" AND B.Code="01" AND R.Unload()[0].Quantity=10);
