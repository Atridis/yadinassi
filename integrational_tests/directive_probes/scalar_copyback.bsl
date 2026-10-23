// Future-scope measurement only: current runtime rejects cross-side non-Val.
&AtServer
Procedure CopyBack(X)
    X = 43;
EndProcedure

&AtServer
Procedure CopyBackFailure(X)
    X = 47;
    Raise "copyback-controlled-failure";
EndProcedure

&AtClient
Procedure Probe() Export
    X = 1;
    CopyBack(X);
    Message("directive.copyback.success: " + ValueToStringInternal(X));
    X = 1;
    Try
        CopyBackFailure(X);
        Message("directive.copyback.failure-status: no-error");
    Except
        Message("directive.copyback.failure-status: error");
    EndTry;
    Message("directive.copyback.failure-value: " + ValueToStringInternal(X));
EndProcedure
