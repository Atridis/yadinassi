nodes=New Array;
For i=1 To 1000 Do node=New Structure("id,neighbors",i,New Array);nodes.Add(node);EndDo;
For i=0 To 998 Do
    node=nodes[i];node.neighbors.Add(nodes[i+1]);
    If i<998 Then node.neighbors.Add(nodes[i+2]);EndIf;
EndDo;
first=nodes[0];last=nodes[999];last.neighbors.Add(first);
seen=New Map;queue=New Array;queue.Add(first);seen.Insert(first,True);
result=0;trace=0;edges=0;
For Each current In queue Do
    Observe(current.id);result=result+1;trace=(trace*1001+current.id)%1000003;
    For Each neighbor In current.neighbors Do
        edges=edges+1;
        If seen.Get(neighbor)=Undefined Then seen.Insert(neighbor,True);queue.Add(neighbor);EndIf;
    EndDo;
EndDo;
alias=first;aliasFound=seen.Get(alias);
clone=New Structure("id,neighbors",1,New Array);
cloneAbsent=(seen.Get(clone)=Undefined);queueCount=queue.Count();
