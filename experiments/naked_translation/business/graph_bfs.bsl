n1=New Structure("id,neighbors",1,New Array);
n2=New Structure("id,neighbors",2,New Array);
n3=New Structure("id,neighbors",3,New Array);
n4=New Structure("id,neighbors",4,New Array);
n1.neighbors.Add(n2);n1.neighbors.Add(n3);
n2.neighbors.Add(n4);n3.neighbors.Add(n4);n4.neighbors.Add(n1);
seen=New Map;queue=New Array;queue.Add(n1);seen.Insert(n1,True);
result=0;trace=0;edges=0;
For Each current In queue Do
    Observe(current.id);
    result=result+1;trace=trace*10+current.id;
    For Each neighbor In current.neighbors Do
        edges=edges+1;
        If seen.Get(neighbor)=Undefined Then
            seen.Insert(neighbor,True);queue.Add(neighbor);
        EndIf;
    EndDo;
EndDo;
alias=n1;aliasFound=seen.Get(alias);
clone=New Structure("id,neighbors",1,New Array);
cloneAbsent=(seen.Get(clone)=Undefined);
queueCount=queue.Count();
