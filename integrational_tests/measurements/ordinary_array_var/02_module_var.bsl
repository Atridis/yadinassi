Var i;
Procedure F()
    For i=1 To 2 Do
        i=10;
    EndDo;
EndProcedure
i=42;
F();
Message("var.module: observed|" + ЗначениеВСтрокуВнутр(i));
