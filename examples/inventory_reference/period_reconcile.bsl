// Separate explicit write operation. The report itself never changes records.
January = Documents.Issue.FindByNumber("PS-I1").GetObject();
January.Lines[0].Quantity = 4; January.Lines[0].Amount = 40;
January.Write(DocumentWriteMode.Posting);
March = Documents.Issue.FindByNumber("PS-I2").GetObject();
March.Write(DocumentWriteMode.UndoPosting);
Message("January issue reposted as 4; March issue unposted. Reopen the statement to see closing 11.");
