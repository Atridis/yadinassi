// Bounded raw regex extension observations; no expected-answer substitution.
Function DescribeMatch(Match)
    Text=Match.Value+":"+String(Match.StartIndex)+":"+String(Match.Length);
    For Each Group In Match.GetGroups() Do
        Text=Text+"|"+Group.Value+":"+String(Group.StartIndex)+":"+String(Group.Length);
    EndDo;
    Return Text;
EndFunction

Function ObserveCase(CaseNo, Stage)
    Stage="read";
    If CaseNo=1 Then Return DescribeMatch(StrFindByRegularExpression("AbC","(?i)abc")); EndIf;
    If CaseNo=2 Then Return String(StrLikeByRegularExpression("AbC","(?i:a)b(?i:c)"))+":"+String(StrLikeByRegularExpression("ABC","(?i:a)b(?i:c)")); EndIf;
    If CaseNo=3 Then Return String(StrLikeByRegularExpression("Ab","(?i)a(?-i:b)"))+":"+String(StrLikeByRegularExpression("AB","(?i)a(?-i:b)"))+":"+String(StrLikeByRegularExpression("A","(?-i)a",True)); EndIf;
    If CaseNo=4 Then
        Return DescribeMatch(StrFindByRegularExpression("x"+Chars.LF+"a"+Chars.LF+"b","(?ms)^a.b$"));
    EndIf;
    If CaseNo=5 Then Return DescribeMatch(StrFindByRegularExpression("ab","(?=(a))a")); EndIf;
    If CaseNo=6 Then Return DescribeMatch(StrFindByRegularExpression("b","(?!(a))b")); EndIf;
    If CaseNo=7 Then Return DescribeMatch(StrFindByRegularExpression("aab","(?=(a|aa))\1b")); EndIf;
    If CaseNo=8 Then Return DescribeMatch(StrFindByRegularExpression("xx abab yy","(ab)\1")); EndIf;
    If CaseNo=9 Then Return DescribeMatch(StrFindByRegularExpression("aA","(?i)(a)\1")); EndIf;
    If CaseNo=10 Then Return DescribeMatch(StrFindByRegularExpression("b","(a)?b\1")); EndIf;
    If CaseNo=11 Then
        Values=StrFindAllByRegularExpression("aa","(?=(a))"); Text=String(Values.Count());
        For Each Value In Values Do Text=Text+"/"+DescribeMatch(Value); EndDo;
        Return Text;
    EndIf;
    If CaseNo=12 Then Return StrReplaceByRegularExpression("aa bb","(\w+)\s+\1|(?=(bb))","<$1:$2>"); EndIf;
    Raise "unknown-owned-regex-extensions-case";
EndFunction

For CaseNo = 1 To 12 Do
    Stage="setup";
    Try
        Value=ObserveCase(CaseNo,Stage); RegexExtensionsEmit(CaseNo,Value);
    Except
        RegexExtensionsDiagnostic(CaseNo,Stage,ПодробноеПредставлениеОшибки(ИнформацияОбОшибке()));
    EndTry;
EndDo;
