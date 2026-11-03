// One disposable, freshly installed flat catalog; call CDMEmit for each observation.
// All output is Boolean. A completed packet is not an assertion of any outcome.
M = Catalogs.OwnedCatalog4f4ccaa9;

// Direct assignment on an existing, unmarked object. Before-Write and after-Write
// reads use GetObject to avoid treating the detached buffer as stored data.
P = M.CreateItem(); P.Code = "101"; P.Description = "direct"; P.Write(); R = P.Ref;
O = R.GetObject(); A = False;
Try O.DeletionMark = True; A = True; Except EndTry;
CDMEmit(1, A); CDMEmit(2, O.DeletionMark); CDMEmit(3, R.GetObject().DeletionMark);
W = False; Try O.Write(); W = True; Except EndTry;
CDMEmit(4, W); CDMEmit(5, R.GetObject().DeletionMark);

// Independent record. Change Description before SetDeletionMark to discriminate
// whether the method persists the dirty buffer, and observe repeat and unmark.
P = M.CreateItem(); P.Code = "102"; P.Description = "stored"; P.Write(); R = P.Ref;
O = R.GetObject(); O.Description = "dirty"; A = False;
Try O.SetDeletionMark(True); A = True; Except EndTry;
CDMEmit(6, A); CDMEmit(7, O.DeletionMark); CDMEmit(8, R.GetObject().DeletionMark);
CDMEmit(9, O.Description = "dirty"); CDMEmit(10, R.GetObject().Description = "dirty");
A = False; Try O.SetDeletionMark(True); A = True; Except EndTry;
CDMEmit(11, A); CDMEmit(12, R.GetObject().DeletionMark);
A = False; Try O.SetDeletionMark(False); A = True; Except EndTry;
CDMEmit(13, A); CDMEmit(14, O.DeletionMark); CDMEmit(15, R.GetObject().DeletionMark);
A = False; Try O.SetDeletionMark(False); A = True; Except EndTry;
CDMEmit(16, A); CDMEmit(17, R.GetObject().DeletionMark);

// Separate new object: direct assignment then ordinary Write.
N = M.CreateItem(); N.Code = "103"; N.Description = "new-direct"; A = False;
Try N.DeletionMark = True; A = True; Except EndTry;
CDMEmit(18, A); CDMEmit(19, N.DeletionMark); CDMEmit(20, N.IsNew());
W = False; Try N.Write(); W = True; Except EndTry;
CDMEmit(21, W); CDMEmit(22, N.IsNew());
R = M.FindByCode("103"); CDMEmit(23, Not R.IsEmpty());
B = False; If Not R.IsEmpty() Then B = R.GetObject().DeletionMark; EndIf; CDMEmit(24, B);

// New object, method call without preceding Write. Lookup independently reveals
// whether the call creates a row; the empty check guards the follow-up read.
N = M.CreateItem(); N.Code = "104"; N.Description = "new-method"; A = False;
Try N.SetDeletionMark(True); A = True; Except EndTry;
CDMEmit(25, A); CDMEmit(26, N.IsNew()); CDMEmit(27, N.Ref.IsEmpty());
CDMEmit(28, N.DeletionMark); R = M.FindByCode("104"); CDMEmit(29, Not R.IsEmpty());
B = False; If Not R.IsEmpty() Then B = R.GetObject().DeletionMark; EndIf; CDMEmit(30, B);
W = False; Try N.Write(); W = True; Except EndTry;
CDMEmit(31, W); R = M.FindByCode("104"); CDMEmit(32, Not R.IsEmpty());
