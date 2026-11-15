# Application common-template resources

The explicit module-runtime importer admits bounded `TextDocument` and `BinaryData` common templates from Designer XML plus the exact owned `Ext/Template.txt` or `Ext/Template.bin` path. Other template families, generic files and undeclared resources do not gain execution permission.

`GetCommonTemplate` / `ПолучитьОбщийМакет` requires an active application. A declared name is case-insensitive; a metadata argument must be the exact metadata value issued by that application. Retrieval returns a fresh text document or binary value. Text resource UTF-8 is decoded and CRLF/CR line endings become LF on retrieval; stored source bytes remain unchanged. Templates have `Metadata.CommonTemplates` name/full-name inspection. There is no disk lookup, spreadsheet implementation, storage format change or UI grant.

Native run `43083042989` supplied twelve observations, including fresh values, binary bytes, case-insensitive lookup and metadata-object arguments. The immutable observation/summary archives and source/prepared-module hashes were reverified during reconstruction. Reconstructed runtime bytes require their own tests; earlier implementation test results are not reused as proof.

Local limits are 128 declarations, 1 MiB per resource and 8 MiB total, plus existing text-document and XML/source bounds. These are host safety policies, not inferred native limits.
