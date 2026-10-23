// Uncaptured measurement source. No native expected values are present.
// Invoke RunObjectTransferProbe literally on the client after module creation.
// Nine literal server calls; 58 fixed primitive observations, all below 1000.
// No module state, Execute, explicit database calls, RPC implementation or async.

&AtServer
Procedure ObjectTransferVal(Val P)
    P.N = 11;
    P.Items[0] = 12;
    P = New Structure("N", 13);
EndProcedure

&AtServer
Function ObjectTransferIndependent(A, B)
    Var Seen;
    A.Items[0] = 21;
    Seen = B.Items[0];
    B.Items[0] = 23;
    Return Seen;
EndFunction

&AtServer
Function ObjectTransferRepeated(A, B)
    A.Items[0] = 31;
    Return B.Items[0];
EndFunction

&AtServer
Procedure ObjectTransferRebind(P)
    Var Items;
    Items = New Array;
    Items.Add(42);
    P = New Structure("N,Items", 41, Items);
EndProcedure

&AtServer
Function ObjectTransferGraph(P, Seen)
    P.Left[0] = 51;
    Seen = P.Right[0];
    // Recreate sharing explicitly so outgoing behavior is independent of input.
    P.Right = P.Left;
    Return P;
EndFunction

&AtServer
Procedure ObjectTransferEscapes(P, Untouched, Val Control)
    Var Items;
    P.N = 61;
    P.Items[0] = 62;
    Control.N = 63;
    Control.Items[0] = 64;
    Items = New Array;
    Items.Add(66);
    P = New Structure("N,Items", 65, Items);
    Raise "object-transfer-core-controlled-failure";
EndProcedure

&AtServer
Function ObjectTransferTiming(Val Early, Late, Val Token)
    Return New Structure("Early,Late", Early.Items[0], Late.Items[0]);
EndFunction

&AtServer
Function ObjectTransferCaught(P)
    P.N = 81;
    P.Items[0] = 82;
    Try
        Raise "object-transfer-core-controlled-failure";
    Except
        Return Find(ErrorDescription(), "object-transfer-core-controlled-failure") > 0;
    EndTry;
    Return False;
EndFunction

&AtClient
Function ObjectTransferNew(Val N)
    Var Items;
    Items = New Array;
    Items.Add(N);
    Return New Structure("N,Items", N, Items);
EndFunction

&AtClient
Function ObjectTransferChange(X, Calls)
    Calls = Calls + 1;
    X.N = 71;
    X.Items[0] = 72;
    X = ObjectTransferNew(73);
    Return 74;
EndFunction

&AtClient
Function ObjectTransferNumber(Val Value)
    If TypeOf(Value) <> Type("Number") Then
        Return Undefined;
    EndIf;
    If Value < 0 Or Value >= 1000 Then
        Return Undefined;
    EndIf;
    Return Value;
EndFunction

&AtClient
Function ObjectTransferField(Val Value, Val Key)
    Var Item;
    If TypeOf(Value) <> Type("Structure") Then
        Return Undefined;
    EndIf;
    Item = Undefined;
    If Not Value.Property(Key, Item) Then
        Return Undefined;
    EndIf;
    Return ObjectTransferNumber(Item);
EndFunction

&AtClient
Function ObjectTransferArrayLeaf(Val Value)
    If TypeOf(Value) <> Type("Array") Then
        Return Undefined;
    EndIf;
    If Value.Count() = 0 Then
        Return Undefined;
    EndIf;
    Return ObjectTransferNumber(Value[0]);
EndFunction

&AtClient
Function ObjectTransferLeaf(Val Value, Val Key)
    Var Item;
    If TypeOf(Value) <> Type("Structure") Then
        Return Undefined;
    EndIf;
    Item = Undefined;
    If Not Value.Property(Key, Item) Then
        Return Undefined;
    EndIf;
    Return ObjectTransferArrayLeaf(Item);
EndFunction

&AtClient
Procedure ObjectTransferRecord(Val Label, Val Value)
    // The future integrated adapter replaces this one sink with Records.Add.
    // The value is always Number, Boolean or Undefined, never an object/error.
    Message("object.transfer.core." + Label + ": " + ValueToStringInternal(Value));
EndProcedure

&AtServer
Function ObjectTransferMixedTiming(Val NamedObject, Val AliasObject, Val ExpressionObject, Val NamedScalar, Val ExpressionScalar, Val Token)
    Return New Structure("NamedObject,AliasObject,ExpressionObject,NamedScalar,ExpressionScalar", NamedObject.Items[0], AliasObject.Items[0], ExpressionObject.Items[0], NamedScalar, ExpressionScalar);
EndFunction

&AtClient
Function ObjectTransferIdentity(Val Value)
    Return Value;
EndFunction

&AtClient
Function ObjectTransferChangeBoth(X, Scalar, Calls)
    Calls = Calls + 1;
    X.Items[0] = 72;
    X = ObjectTransferNew(73);
    Scalar = 74;
    Return 75;
EndFunction

&AtClient
Procedure RunObjectTransferProbe() Export
    Var Scalar;
    Var X, Y, Kept, Child, Control, Untouched, Result, Seen, Calls;
    Var Failed, Matched, BeforeX, BeforeY, AfterY;
    Var AfterXSibling, AfterXResultLeft, AfterXResultRight;
    Var AfterResultSibling, AfterResultXLeft, AfterResultXRight;

    ObjectTransferRecord("entered", True);

    // 1. Val: nested mutation followed by formal rebinding.
    X = ObjectTransferNew(1);
    Child = X.Items;
    Failed = False;
    Try
        ObjectTransferVal(X);
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("val.error", Failed);
    ObjectTransferRecord("val.root", ObjectTransferField(X, "N"));
    ObjectTransferRecord("val.leaf", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("val.retained", ObjectTransferArrayLeaf(Child));

    // 2. Two different caller variables initially alias the same object.
    X = ObjectTransferNew(2);
    Y = X;
    Child = X.Items;
    Seen = Undefined;
    BeforeX = Undefined;
    BeforeY = Undefined;
    AfterY = Undefined;
    Failed = False;
    Try
        Seen = ObjectTransferIndependent(X, Y);
        BeforeX = ObjectTransferLeaf(X, "Items");
        BeforeY = ObjectTransferLeaf(Y, "Items");
        X.Items[0] = 24;
        AfterY = ObjectTransferLeaf(Y, "Items");
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("independent.error", Failed);
    ObjectTransferRecord("independent.server.second", ObjectTransferNumber(Seen));
    ObjectTransferRecord("independent.x.before", BeforeX);
    ObjectTransferRecord("independent.y.before", BeforeY);
    ObjectTransferRecord("independent.y.after", AfterY);
    ObjectTransferRecord("independent.retained", ObjectTransferArrayLeaf(Child));

    // 3. One caller sink repeated; rightmost formal is not mutated or rebound.
    X = ObjectTransferNew(3);
    Child = X.Items;
    Seen = Undefined;
    Failed = False;
    Try
        Seen = ObjectTransferRepeated(X, X);
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("repeated.error", Failed);
    ObjectTransferRecord("repeated.server.second", ObjectTransferNumber(Seen));
    ObjectTransferRecord("repeated.leaf", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("repeated.retained", ObjectTransferArrayLeaf(Child));

    // 4. Explicit non-Val root replacement, with an unpassed old root alias.
    X = ObjectTransferNew(4);
    Kept = X;
    Failed = False;
    Try
        ObjectTransferRebind(X);
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("rebind.error", Failed);
    ObjectTransferRecord("rebind.root", ObjectTransferField(X, "N"));
    ObjectTransferRecord("rebind.leaf", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("rebind.retained", ObjectTransferField(Kept, "N"));

    // 5. Shared child on input; explicit server sharing on output and return.
    Child = New Array;
    Child.Add(5);
    X = New Structure("Left,Right", Child, Child);
    Seen = Undefined;
    Result = Undefined;
    AfterXSibling = Undefined;
    AfterXResultLeft = Undefined;
    AfterXResultRight = Undefined;
    AfterResultSibling = Undefined;
    AfterResultXLeft = Undefined;
    AfterResultXRight = Undefined;
    Failed = False;
    Try
        Result = ObjectTransferGraph(X, Seen);
        X.Left[0] = 52;
        AfterXSibling = ObjectTransferLeaf(X, "Right");
        AfterXResultLeft = ObjectTransferLeaf(Result, "Left");
        AfterXResultRight = ObjectTransferLeaf(Result, "Right");
        Result.Left[0] = 53;
        AfterResultSibling = ObjectTransferLeaf(Result, "Right");
        AfterResultXLeft = ObjectTransferLeaf(X, "Left");
        AfterResultXRight = ObjectTransferLeaf(X, "Right");
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("graph.error", Failed);
    ObjectTransferRecord("graph.server.sibling", ObjectTransferNumber(Seen));
    ObjectTransferRecord("graph.x.sibling", AfterXSibling);
    ObjectTransferRecord("graph.result.left.after.x", AfterXResultLeft);
    ObjectTransferRecord("graph.result.right.after.x", AfterXResultRight);
    ObjectTransferRecord("graph.result.sibling", AfterResultSibling);
    ObjectTransferRecord("graph.x.left.after.result", AfterResultXLeft);
    ObjectTransferRecord("graph.x.right.after.result", AfterResultXRight);
    ObjectTransferRecord("graph.retained", ObjectTransferArrayLeaf(Child));

    // 6. Escaping server failure. Readers handle Undefined before dereferencing.
    X = ObjectTransferNew(6);
    Kept = X;
    Child = X.Items;
    Untouched = ObjectTransferNew(7);
    Control = ObjectTransferNew(8);
    Failed = False;
    Matched = False;
    Try
        ObjectTransferEscapes(X, Untouched, Control);
    Except
        Failed = True;
        Matched = Find(ErrorDescription(), "object-transfer-core-controlled-failure") > 0;
    EndTry;
    ObjectTransferRecord("escaped.error", Failed);
    ObjectTransferRecord("escaped.matched", Matched);
    ObjectTransferRecord("escaped.value.undefined", X = Undefined);
    ObjectTransferRecord("escaped.value.leaf", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("escaped.retained.root", ObjectTransferField(Kept, "N"));
    ObjectTransferRecord("escaped.retained.leaf", ObjectTransferArrayLeaf(Child));
    ObjectTransferRecord("escaped.untouched.undefined", Untouched = Undefined);
    ObjectTransferRecord("escaped.untouched.leaf", ObjectTransferLeaf(Untouched, "Items"));
    ObjectTransferRecord("escaped.val.leaf", ObjectTransferLeaf(Control, "Items"));

    // 7. Earlier Val object handle versus later mutation and rebinding of X.
    X = ObjectTransferNew(9);
    Child = X.Items;
    Calls = 0;
    Result = Undefined;
    Failed = False;
    Try
        Result = ObjectTransferTiming(X, X, ObjectTransferChange(X, Calls));
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("timing.error", Failed);
    ObjectTransferRecord("timing.early", ObjectTransferField(Result, "Early"));
    ObjectTransferRecord("timing.late", ObjectTransferField(Result, "Late"));
    ObjectTransferRecord("timing.caller", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("timing.retained", ObjectTransferArrayLeaf(Child));
    ObjectTransferRecord("timing.calls", ObjectTransferNumber(Calls));

    // 8. A server-caught error returns normally; also checks post-failure recovery.
    X = ObjectTransferNew(10);
    Child = X.Items;
    Matched = Undefined;
    Failed = False;
    Try
        Matched = ObjectTransferCaught(X);
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("recovery.error", Failed);
    ObjectTransferRecord("recovery.matched", Matched);
    ObjectTransferRecord("recovery.leaf", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("recovery.retained", ObjectTransferArrayLeaf(Child));

    ObjectTransferRecord("complete", True);

    // 9. Named storage versus expression results before a later argument effect.
    X = ObjectTransferNew(9);
    Kept = X;
    Scalar = 11;
    Calls = 0;
    Result = Undefined;
    Failed = False;
    Try
        Result = ObjectTransferMixedTiming(X, Kept, ObjectTransferIdentity(X), Scalar, ObjectTransferIdentity(Scalar), ObjectTransferChangeBoth(X, Scalar, Calls));
    Except
        Failed = True;
    EndTry;
    ObjectTransferRecord("mixed.error", Failed);
    ObjectTransferRecord("mixed.named.object", ObjectTransferField(Result, "NamedObject"));
    ObjectTransferRecord("mixed.alias.object", ObjectTransferField(Result, "AliasObject"));
    ObjectTransferRecord("mixed.expression.object", ObjectTransferField(Result, "ExpressionObject"));
    ObjectTransferRecord("mixed.named.scalar", ObjectTransferField(Result, "NamedScalar"));
    ObjectTransferRecord("mixed.expression.scalar", ObjectTransferField(Result, "ExpressionScalar"));
    ObjectTransferRecord("mixed.caller.object", ObjectTransferLeaf(X, "Items"));
    ObjectTransferRecord("mixed.caller.scalar", ObjectTransferNumber(Scalar));
    ObjectTransferRecord("mixed.retained", ObjectTransferLeaf(Kept, "Items"));
    ObjectTransferRecord("mixed.calls", ObjectTransferNumber(Calls));
EndProcedure
