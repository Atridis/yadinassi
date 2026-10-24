// Uncaptured semantic design only. No native expected outputs are asserted.
// Invoke DNCollect() literally on the client after module creation.
// Eight direct client-to-server calls, no platform objects or new transport.
// Native output is eight finite digits, NOT a synthetic compatibility verdict.

&AtServer
Function DNEchoDate(Val Value)
    If TypeOf(Value) <> Type("Date") Then Return 0; EndIf;
    If Value <> Date(2024, 1, 2, 3, 4, 5) Then Return 0; EndIf;
    Return Value;
EndFunction

&AtServer
Function DNEchoNull(Val Value)
    If TypeOf(Value) <> Type("Null") Then Return 0; EndIf;
    Return Value;
EndFunction

&AtServer
Procedure DNDateToNull(Value)
    If TypeOf(Value) <> Type("Date") Then Raise "dn-invalid-date-input"; EndIf;
    If Value <> Date(2024, 1, 2, 3, 4, 5) Then Raise "dn-invalid-date-value"; EndIf;
    Value = Null;
EndProcedure

&AtServer
Procedure DNNullToDate(Value)
    If TypeOf(Value) <> Type("Null") Then Raise "dn-invalid-null-input"; EndIf;
    Value = Date(2031, 6, 7, 8, 9, 10);
EndProcedure

&AtServer
Function DNValDate(Val Value)
    If TypeOf(Value) <> Type("Date") Then Return False; EndIf;
    If Value <> Date(2024, 1, 2, 3, 4, 5) Then Return False; EndIf;
    Value = Null;
    Return True;
EndFunction

&AtServer
Function DNValNull(Val Value)
    If TypeOf(Value) <> Type("Null") Then Return False; EndIf;
    Value = Date(2031, 6, 7, 8, 9, 10);
    Return True;
EndFunction

&AtServer
Function DNValGraph(Val Graph)
    Var Seen;
    Seen = False;
    If TypeOf(Graph.Leaves[0]) = Type("Date") Then
        If Graph.Leaves[0] = Date(2024, 1, 2, 3, 4, 5) Then
            Seen = TypeOf(Graph.Leaves[1]) = Type("Null");
        EndIf;
    EndIf;
    Graph.Leaves[0] = Null;
    Graph.Leaves[1] = Date(2031, 6, 7, 8, 9, 10);
    Graph.Seen = Seen;
    Return Graph;
EndFunction

&AtServer
Function DNRefGraph(Graph)
    Var Seen;
    Seen = False;
    If TypeOf(Graph.Leaves[0]) = Type("Date") Then
        If Graph.Leaves[0] = Date(2024, 1, 2, 3, 4, 5) Then
            Seen = TypeOf(Graph.Leaves[1]) = Type("Null");
        EndIf;
    EndIf;
    Graph.Leaves[0] = Null;
    Graph.Leaves[1] = Date(2031, 6, 7, 8, 9, 10);
    Return Seen;
EndFunction

&AtClient
Function DNIsDateA(Val Value)
    If TypeOf(Value) <> Type("Date") Then Return False; EndIf;
    Return Value = Date(2024, 1, 2, 3, 4, 5);
EndFunction

&AtClient
Function DNIsDateB(Val Value)
    If TypeOf(Value) <> Type("Date") Then Return False; EndIf;
    Return Value = Date(2031, 6, 7, 8, 9, 10);
EndFunction

&AtClient
Function DNIsNull(Val Value)
    Return TypeOf(Value) = Type("Null");
EndFunction

&AtClient
Function DNIsTrue(Val Value)
    If TypeOf(Value) <> Type("Boolean") Then Return False; EndIf;
    Return Value;
EndFunction

&AtClient
Function DNNewGraph()
    Var Leaves;
    Leaves = New Array;
    Leaves.Add(Date(2024, 1, 2, 3, 4, 5));
    Leaves.Add(Null);
    Return New Structure("Leaves,Seen", Leaves, False);
EndFunction

&AtClient
Function DNOriginalGraph(Val Graph)
    Var Leaves;
    If TypeOf(Graph) <> Type("Structure") Then Return False; EndIf;
    If Not Graph.Property("Leaves", Leaves) Then Return False; EndIf;
    If TypeOf(Leaves) <> Type("Array") Then Return False; EndIf;
    If Leaves.Count() <> 2 Then Return False; EndIf;
    Return DNIsDateA(Leaves[0]) And DNIsNull(Leaves[1]);
EndFunction

&AtClient
Function DNSwappedGraph(Val Graph)
    Var Leaves;
    If TypeOf(Graph) <> Type("Structure") Then Return False; EndIf;
    If Not Graph.Property("Leaves", Leaves) Then Return False; EndIf;
    If TypeOf(Leaves) <> Type("Array") Then Return False; EndIf;
    If Leaves.Count() <> 2 Then Return False; EndIf;
    Return DNIsNull(Leaves[0]) And DNIsDateB(Leaves[1]);
EndFunction

&AtClient
Function DNCollect() Export
    Var Observations, Value, Result, State, Graph, Original, Mask, Seen;
    Observations = New Array;
    // Slots 0..5: 0 = caught error, 1 = completed but predicate false, 2 = true.
    State = 0;
    Try
        Value = Date(2024, 1, 2, 3, 4, 5);
        Result = DNEchoDate(Value);
        State = 1;
        If DNIsDateA(Result) Then State = 2; EndIf;
    Except
        State = 0;
    EndTry;
    Observations.Add(State);
    State = 0;
    Try
        Value = Null;
        Result = DNEchoNull(Value);
        State = 1;
        If DNIsNull(Result) Then State = 2; EndIf;
    Except
        State = 0;
    EndTry;
    Observations.Add(State);
    State = 0;
    Try
        Value = Date(2024, 1, 2, 3, 4, 5);
        DNDateToNull(Value);
        State = 1;
        If DNIsNull(Value) Then State = 2; EndIf;
    Except
        State = 0;
    EndTry;
    Observations.Add(State);
    State = 0;
    Try
        Value = Null;
        DNNullToDate(Value);
        State = 1;
        If DNIsDateB(Value) Then State = 2; EndIf;
    Except
        State = 0;
    EndTry;
    Observations.Add(State);
    State = 0;
    Try
        Value = Date(2024, 1, 2, 3, 4, 5);
        Result = DNValDate(Value);
        State = 1;
        If DNIsTrue(Result) And DNIsDateA(Value) Then State = 2; EndIf;
    Except
        State = 0;
    EndTry;
    Observations.Add(State);
    State = 0;
    Try
        Value = Null;
        Result = DNValNull(Value);
        State = 1;
        If DNIsTrue(Result) And DNIsNull(Value) Then State = 2; EndIf;
    Except
        State = 0;
    EndTry;
    Observations.Add(State);
    // Slot 6: bit1 input checked on server, bit2 returned leaves, bit4 Val isolation.
    Mask = 8;
    Try
        Graph = DNNewGraph();
        Result = DNValGraph(Graph);
        Mask = 0;
        If Result.Property("Seen", Seen) Then
            If DNIsTrue(Seen) Then Mask = Mask + 1; EndIf;
        EndIf;
        If DNSwappedGraph(Result) Then Mask = Mask + 2; EndIf;
        If DNOriginalGraph(Graph) Then Mask = Mask + 4; EndIf;
    Except
        Mask = 8;
    EndTry;
    Observations.Add(Mask);
    // Slot 7: bit1 input checked, bit2 copied-back leaves, bit4 old alias isolated.
    Mask = 8;
    Try
        Graph = DNNewGraph();
        Original = Graph;
        Result = DNRefGraph(Graph);
        Mask = 0;
        If DNIsTrue(Result) Then Mask = Mask + 1; EndIf;
        If DNSwappedGraph(Graph) Then Mask = Mask + 2; EndIf;
        If DNOriginalGraph(Original) Then Mask = Mask + 4; EndIf;
    Except
        Mask = 8;
    EndTry;
    Observations.Add(Mask);
    Return Observations;
EndFunction

&AtClient
Function DNEncode(Observations)
    Var Encoded, Value, Slot;
    If Observations.Count() <> 8 Then Raise "dn-invalid-count"; EndIf;
    Encoded = "dn.v1:";
    Slot = 0;
    For Each Value In Observations Do
        If TypeOf(Value) <> Type("Number") Then Raise "dn-invalid-type"; EndIf;
        If Value < 0 Or Value > 8 Or Int(Value) <> Value Then Raise "dn-invalid-range"; EndIf;
        If Slot < 6 And Value > 2 Then Raise "dn-invalid-scalar-range"; EndIf;
        Encoded = Encoded + Mid("012345678", Value + 1, 1);
        Slot = Slot + 1;
    EndDo;
    Return Encoded;
EndFunction

&AtClient
Procedure DNAppend(RecordsOut)
    RecordsOut.Add(DNEncode(DNCollect()));
EndProcedure
