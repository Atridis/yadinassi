// Owned flat catalog and Delete grant. No raw exception text is emitted.
// Category priority: rights, lock, missing method, then other. Zero means success.
Function CDMClass(Val ErrorText)
    If TypeOf(ErrorText) <> Type("String") Then Return 4; EndIf;
    T = Lower(Left(ErrorText, 2048));
    If Find(T, "недостаточно прав") > 0 Or Find(T, "нарушение прав доступа") > 0
       Or Find(T, "access denied") > 0 Or Find(T, "insufficient rights") > 0
       Or Find(T, "permission denied") > 0 Then Return 1; EndIf;
    If Find(T, "блокировк") > 0 Or Find(T, "lock conflict") > 0
       Or Find(T, "unable to lock") > 0 Or Find(T, "object is locked") > 0 Then Return 2; EndIf;
    If Find(T, "метод объекта не обнаружен") > 0 Or Find(T, "не обнаружен метод") > 0
       Or Find(T, "method not found") > 0 Or Find(T, "object method not found") > 0 Then Return 3; EndIf;
    Return 4;
EndFunction

M = Catalogs.OwnedCatalog4f4ccaa9;
P = M.CreateItem(); P.Code = "201"; P.Description = "stored"; P.Write(); R = P.Ref;
O = R.GetObject(); O.Description = "dirty"; C = 0;
Try O.SetDeletionMark(True); Except C = CDMClass(ErrorDescription()); EndTry;
CDMEmit(1, C = 0); CDMEmit(2, C = 1); CDMEmit(3, C = 2);
CDMEmit(4, C = 3); CDMEmit(5, C = 4);
CDMEmit(6, O.DeletionMark); CDMEmit(7, R.GetObject().DeletionMark);
CDMEmit(8, O.Description = "dirty"); CDMEmit(9, R.GetObject().Description = "dirty");
CDMEmit(10, Not R.GetObject().IsNew());

N = M.CreateItem(); N.Code = "202"; N.Description = "new"; C = 0;
Try N.SetDeletionMark(True); Except C = CDMClass(ErrorDescription()); EndTry;
CDMEmit(11, C = 0); CDMEmit(12, C = 1); CDMEmit(13, C = 2);
CDMEmit(14, C = 3); CDMEmit(15, C = 4);
CDMEmit(16, N.IsNew()); CDMEmit(17, N.Ref.IsEmpty()); CDMEmit(18, N.DeletionMark);
R = M.FindByCode("202"); CDMEmit(19, Not R.IsEmpty());
B = False; If Not R.IsEmpty() Then B = R.GetObject().DeletionMark; EndIf; CDMEmit(20, B);
