// Unexecuted measurement source. No native values are asserted.
// Managed form module. Invoke CollectDualDirectiveProbe on the client after creation.
// No module initializer; all observations occur in explicit caller routines.
&AtServer
Var DualProbeServerState;

&НаКлиентеНаСервереБезКонтекста
Procedure DualProbeLeaf(ReferenceValue)
    ReferenceValue = ReferenceValue + 1;
EndProcedure

&AtClientAtServerNoContext
Function DualProbeOperation(ReferenceValue, Val ContainerValue, Val Escape)
    Var ProfileMask;
    ReferenceValue = ReferenceValue + 10;
    DualProbeLeaf(ReferenceValue);
    ContainerValue[0] = ContainerValue[0] + 10;
    If Escape Then
        Raise "dual-directive-controlled-failure";
    EndIf;
    ProfileMask = 0;
#If Client Then
    ProfileMask = ProfileMask + 1;
#EndIf
#If Server Then
    ProfileMask = ProfileMask + 2;
#EndIf
#If AtClient Then
    ProfileMask = ProfileMask + 4;
#EndIf
#If AtServer Then
    ProfileMask = ProfileMask + 8;
#EndIf
    Return New Structure("Container,Mask", ContainerValue, ProfileMask);
EndFunction

&AtClient
Function DualProbeFromClient()
    Var Observations, ScalarValue, ContainerValue, OperationResult, Caught;
    Observations = New Array;
    ScalarValue = 1;
    ContainerValue = New Array;
    ContainerValue.Add(2);
    OperationResult = DualProbeOperation(ScalarValue, ContainerValue, False);
    Observations.Add(OperationResult.Mask);
    OperationResult.Container[0] = OperationResult.Container[0] + 20;
    Observations.Add(ContainerValue[0]);
    ScalarValue = 6;
    ContainerValue = New Array;
    ContainerValue.Add(7);
    Caught = False;
    Try
        DualProbeOperation(ScalarValue, ContainerValue, True);
    Except
        If Find(ErrorDescription(), "dual-directive-controlled-failure") > 0 Then
            Caught = True;
        Else
            Raise;
        EndIf;
    EndTry;
    If Not Caught Then
        Raise "dual-directive-expected-exception-missing";
    EndIf;
    Observations.Add(ScalarValue);
    Return Observations;
EndFunction

&AtServer
Function DualProbeFromServer()
    Var Observations, ScalarValue, ContainerValue, OperationResult, Caught;
    DualProbeServerState = 40;
    Observations = New Array;
    ScalarValue = 1;
    ContainerValue = New Array;
    ContainerValue.Add(2);
    OperationResult = DualProbeOperation(ScalarValue, ContainerValue, False);
    Observations.Add(OperationResult.Mask);
    ScalarValue = 6;
    ContainerValue = New Array;
    ContainerValue.Add(7);
    Caught = False;
    Try
        DualProbeOperation(ScalarValue, ContainerValue, True);
    Except
        If Find(ErrorDescription(), "dual-directive-controlled-failure") > 0 Then
            Caught = True;
        Else
            Raise;
        EndIf;
    EndTry;
    If Not Caught Then
        Raise "dual-directive-expected-exception-missing";
    EndIf;
    Observations.Add(ScalarValue);
    DualProbeServerState = DualProbeServerState + 1;
    Observations.Add(DualProbeServerState);
    Return Observations;
EndFunction

&AtServerNoContext
Function DualProbeFromServerNoContext()
    Var Observations, ScalarValue, ContainerValue, OperationResult, Caught;
    Observations = New Array;
    ScalarValue = 1;
    ContainerValue = New Array;
    ContainerValue.Add(2);
    OperationResult = DualProbeOperation(ScalarValue, ContainerValue, False);
    Observations.Add(OperationResult.Mask);
    OperationResult.Container[0] = OperationResult.Container[0] + 20;
    Observations.Add(ContainerValue[0]);
    ScalarValue = 6;
    ContainerValue = New Array;
    ContainerValue.Add(7);
    Caught = False;
    Try
        DualProbeOperation(ScalarValue, ContainerValue, True);
    Except
        If Find(ErrorDescription(), "dual-directive-controlled-failure") > 0 Then
            Caught = True;
        Else
            Raise;
        EndIf;
    EndTry;
    If Not Caught Then
        Raise "dual-directive-expected-exception-missing";
    EndIf;
    Observations.Add(ScalarValue);
    Return Observations;
EndFunction

&AtClient
Function CollectDualDirectiveProbe() Export
    Var Observations, Part, Item;
    Observations = New Array;
    Part = DualProbeFromClient();
    For Each Item In Part Do
        Observations.Add(Item);
    EndDo;
    Part = DualProbeFromServer();
    For Each Item In Part Do
        Observations.Add(Item);
    EndDo;
    Part = DualProbeFromServerNoContext();
    For Each Item In Part Do
        Observations.Add(Item);
    EndDo;
    Return Observations;
EndFunction
