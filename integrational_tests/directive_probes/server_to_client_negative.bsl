// Compile separately: record the actual compilation stage and bounded outcome.
&AtClient
Function ClientOnly()
    Return 42;
EndFunction

&AtServer
Function InvalidServerCall()
    Return ClientOnly();
EndFunction
