// Owned session lifecycle observer: no module variables or exported routines.
Procedure SessionParametersSetting(RequiredParameters)
    If RequiredParameters = Undefined Then
        SessionParameters.OwnedStartup = 1;
        SessionParameters.OwnedStartupUndefined = True;
        SessionParameters.OwnedCalls = 0;
        SessionParameters.OwnedMissingCalls = 0;
        SessionParameters.OwnedWitness = 0;
        Return;
    EndIf;
    For Each ParameterName In RequiredParameters Do
        If ParameterName = "OwnedLazy" Then
            SessionParameters.OwnedCalls = SessionParameters.OwnedCalls + 1;
            SessionParameters.OwnedLazy = "ready";
            SessionParameters.OwnedLinked = "pair";
        ElsIf ParameterName = "OwnedMissing" Then
            SessionParameters.OwnedMissingCalls = SessionParameters.OwnedMissingCalls + 1;
        ElsIf ParameterName = "OwnedNumber" Then
            SessionParameters.OwnedNumber = 77;
        ElsIf ParameterName = "OwnedFailure" Then
            SessionParameters.OwnedWitness = 42;
            Raise "owned-session-failure";
        EndIf;
    EndDo;
EndProcedure
