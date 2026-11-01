// !todo Unsupported backrefs/lookaround/named/inline/property syntax, resource stress.
Функция RFEncode(Val T)
If TypeOf(T)<>Type("String") Or StrLen(T)>40 Then Raise "regex-observer-bound";EndIf;
R="S"+String(StrLen(T))+":";
For P=1 To StrLen(T) Do
C=CharCode(T,P);H="";If C<0 Or C>65535 Then Raise "regex-unit-bound";EndIf;
For D=1 To 4 Do Q=Int(C/16);H=Mid("0123456789abcdef",C-Q*16+1,1)+H;C=Q;EndDo;
R=R+H;
EndDo;
Return R;
EndFunction
Функция RFResult(Val R)
Return String(R.StartIndex)+":"+String(R.Length)+":"+R.Value;
EndFunction
Функция RFArray(Val A)
If A.Count()>5 Then Raise "regex-array-bound";EndIf;
R=String(A.Count());For Each E In A Do R=R+"|"+RFResult(E);EndDo;Return R;
EndFunction
Функция RFCase(Val N)
If N=1 Then Return String(StrLikeByRegularExpression("ab12","[a-z]+[0-9]{2}"));
ElsIf N=2 Then Return String(StrLikeByRegularExpression("xabx","ab"));
ElsIf N=3 Then Return String(StrLikeByRegularExpression("a7","[^0-9][0-9]"))+":"+String(StrLikeByRegularExpression("Я","\w"))+":"+String(StrLikeByRegularExpression("١","\d"))+":"+String(StrLikeByRegularExpression(" ","\s"))+":"+String(StrLikeByRegularExpression("я","\bя\b"));
ElsIf N=4 Then S=String(StrLikeByRegularExpression("Яа","яА"))+":"+String(StrLikeByRegularExpression("Яа","яА",True));Try S=S+":"+String(StrLikeByRegularExpression("Яа","яА",1));Except S=S+":flag-error";EndTry;Return S;
ElsIf N=5 Then T="a"+Chars.LF+"b";P="^a$"+Chars.LF+"^b$";Return String(StrLikeByRegularExpression(T,P))+":"+String(StrLikeByRegularExpression(T,P,False,True));
ElsIf N=6 Then Return String(StrLikeByRegularExpression("😀","."))+":"+String(StrLikeByRegularExpression("😀",".."));
ElsIf N=7 Then Return RFResult(StrFindByRegularExpression("abc12de","[0-9]+"));
ElsIf N=8 Then Return RFResult(StrFindByRegularExpression("abc","z"));
ElsIf N=9 Then Return RFResult(StrFindByRegularExpression("ab ab ab","ab",SearchDirection.FromBegin,3));
ElsIf N=10 Then Return RFResult(StrFindByRegularExpression("ab ab ab","ab",SearchDirection.FromBegin,1,2));
ElsIf N=11 Then Return RFResult(StrFindByRegularExpression("ab ab ab","ab",SearchDirection.FromEnd));
ElsIf N=12 Then Return RFResult(StrFindByRegularExpression("ab ab ab","ab",SearchDirection.FromEnd,6,2));
ElsIf N=13 Then Return RFResult(StrFindByRegularExpression("ab","a|ab"));
ElsIf N=14 Then Return RFResult(StrFindByRegularExpression("aaa","a+"))+"|"+RFResult(StrFindByRegularExpression("aaa","a+?"))+"|"+RFResult(StrFindByRegularExpression("aaa","a+",SearchDirection.FromEnd))+"|"+RFResult(StrFindByRegularExpression("aaa","a+?",SearchDirection.FromEnd));
ElsIf N=15 Then Return RFResult(StrFindByRegularExpression("😀a😀","a"))+"|"+RFResult(StrFindByRegularExpression("😀a😀","😀"));
ElsIf N=16 Then Return RFArray(StrFindAllByRegularExpression("a1 a22","[0-9]+"));
ElsIf N=17 Then Return RFArray(StrFindAllByRegularExpression("ab","z"));
ElsIf N=18 Then Return RFArray(StrFindAllByRegularExpression("ab",""));
ElsIf N=19 Then Return RFArray(StrFindAllByRegularExpression("ab","$"));
ElsIf N=20 Then Return RFArray(StrFindAllByRegularExpression("ba","a*"));
ElsIf N=21 Then Return RFArray(StrFindAllByRegularExpression("",""));
ElsIf N=22 Then Return RFArray(StrFindByRegularExpression("ab","(a)(b)").GetGroups());
ElsIf N=23 Then Return RFArray(StrFindByRegularExpression("b","(a)?(b)").GetGroups());
ElsIf N=24 Then Return RFArray(StrFindByRegularExpression("ab","(a(b))").GetGroups());
ElsIf N=25 Then Return RFArray(StrFindByRegularExpression("aa","(a)+").GetGroups());
ElsIf N=26 Then Return RFArray(StrFindByRegularExpression("ab","(?:a)(b)").GetGroups());
ElsIf N=27 Then Return RFArray(StrFindByRegularExpression("😀a","(😀)(a)").GetGroups());
ElsIf N=28 Then R=StrFindByRegularExpression("a","(a)");A=R.GetGroups();K=A.Count();A.Clear();Return String(K)+":"+String(R.GetGroups().Count());
ElsIf N=29 Then Return StrReplaceByRegularExpression("a1b22","[0-9]+","X");
ElsIf N=30 Then Return StrReplaceByRegularExpression("ab","ab","[$0]");
ElsIf N=31 Then Return StrReplaceByRegularExpression("ab","(a)(b)","$2-$1");
ElsIf N=32 Then Return StrReplaceByRegularExpression("ab","(a)(b)","$$:$0:$1");
ElsIf N=33 Then Try S=StrReplaceByRegularExpression("ab","(a)(b)","$10");Except S="short-error";EndTry;Try S=S+"|"+StrReplaceByRegularExpression("abcdefghij","(a)(b)(c)(d)(e)(f)(g)(h)(i)(j)","$10:$1");Except S=S+"|ten-error";EndTry;Try S=S+"|"+StrReplaceByRegularExpression("ab","(a)(b)","$9");Except S=S+"|missing-error";EndTry;Return S;
ElsIf N=34 Then Return StrReplaceByRegularExpression("ab","","_");
ElsIf N=35 Then Return StrReplaceByRegularExpression("я"+Chars.LF+"Я","^я$","X",True,True);
ElsIf N=36 Then Try R=StrLikeByRegularExpression("a","(");Return "unexpected";Except Return "pattern-error";EndTry;
ElsIf N=37 Then Try R=StrFindByRegularExpression("a","a",SearchDirection.FromBegin,0);S="unexpected";Except S="start-error";EndTry;Try S=S+"|"+RFResult(StrFindByRegularExpression("a","a",SearchDirection.FromBegin,"1"));Except S=S+"|string-error";EndTry;Try S=S+"|"+RFResult(StrFindByRegularExpression("a","a",SearchDirection.FromBegin,1.9));Except S=S+"|fraction-error";EndTry;Return S;
ElsIf N=38 Then Try R=StrFindByRegularExpression("a","a",SearchDirection.FromBegin,1,0);Return "unexpected";Except Return "entry-error";EndTry;
ElsIf N=39 Then R=StrFindByRegularExpression("a","(a)");G=R.GetGroups()[0];S="";Try R.Value="z";S="write";Except S="readonly";EndTry;Try G.StartIndex=9;S=S+":write";Except S=S+":readonly";EndTry;Return S;
ElsIf N=40 Then R=StrFindByRegularExpression("a","(a)");G=R.GetGroups()[0];Return String(TypeOf(R)=Type("ResultOfSearchByRegularExpression"))+":"+String(TypeOf(G)=Type("ResultOfSearchByRegularExpressionGroup"))+":"+String(TypeOf(R.GetGroups())=Type("Array"));
EndIf;
Return "unknown";
EndFunction
Процедура RFObserve(Val N)
Label=Right("0"+String(N),2);
Try V=RFCase(N);Except Сообщить("RF-"+Label+": [action-error]");Return;EndTry;
Try R=RFEncode(V);Except Сообщить("RF-"+Label+": [observer-error]");Return;EndTry;
Сообщить("RF-"+Label+": [ok|"+R+"]");
EndProcedure
Сообщить("RF-C1: ["+RFEncode("")+"]");
Сообщить("RF-C2: ["+RFEncode("A ;""😀")+"]");
For N=1 To 40 Do RFObserve(N);EndDo;
