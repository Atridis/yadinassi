# Bounded source document OnRead

Source document ObjectModule `OnRead()` / `ПриЧтении()` runs after persisted
fields and tabular sections are loaded by `GetObject()`, selection `GetObject()`
or an existing object's `Read()`. A new object's module is initialized before
loading persisted data; an existing object's module instance is retained.
`CreateDocument()`, queries and `FindByNumber()` do not run the read event.

An owned read transaction encloses initialization, loading and the event. An
existing explicit transaction remains open on success. Failure rolls back the
active transaction, including explicit catalog/constant writes by the handler.
A failed existing-object read closes that object and invalidates section handles;
it is not safe to use partially updated module state. Errors are not swallowed. A swallowed sibling write failure cannot restart a
transaction or continue catalog, constant, query or document access from the
aborted read frame.

Edits to the loaded document remain in memory; no automatic document write is
performed. Explicit document writes during this read lifecycle are refused.
Same-document reentry and more than 32 nested document reads are refused. Existing
synchronous owner/server, safe-mode and transaction-admission checks remain.
Unsupported write events such as BeforeWrite and posting still block Write.

The persisted event marker and schema fingerprints are unchanged. Previously
stored admitted source profiles can reopen without a migration. This is a bounded
source scratch lifecycle, not a claim of complete native document-event parity.
