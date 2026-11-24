Var i;
Procedure F()
    Var i;
    For i=1 To 2 Do
        i=10;
    EndDo;
EndProcedure
i=42;
F();
Message("var.lexical: observed|" + ЗначениеВСтрокуВнутр(i));
