# Text, JSON and XML over existing BSL streams

This block connects the existing readers/writers to the existing MemoryStream,
FileStream and Stream objects. It adds no parser, network service, arbitrary
Python stream adapter, public type or filesystem permission. BinaryData itself
is not a stream argument; use `OpenStreamForRead()`.

This is a bounded local compatibility profile based on the official signatures.
Tests of the existing native file/string profiles remain regression evidence,
not evidence of new stream buffering or lifetime parity.

## API and ordinary defaults

| Object | Stream entry point | Optional arguments after stream |
| --- | --- | --- |
| TextReader / ЧтениеТекста | constructor or Open / Открыть | encoding, lineSplitter, convertibleSplitter |
| TextWriter / ЗаписьТекста | constructor or Open / Открыть | encoding, lineSplitter, convertibleSplitter, writeBOM |
| JSONReader / ЧтениеJSON | OpenStream / ОткрытьПоток | encoding |
| JSONWriter / ЗаписьJSON | OpenStream / ОткрытьПоток | encoding, addBOM, JSONWriterSettings |
| XMLReader / ЧтениеXML | OpenStream / ОткрытьПоток | XMLReaderSettings, schemaSet, encoding |
| XMLWriter / ЗаписьXML | OpenStream / ОткрытьПоток | encoding string or XMLWriterSettings, addBOM |

The four JSON/XML objects still have only empty constructors. SchemaSet remains
unsupported and is rejected before consuming the stream. Settings and ordinary
content handling use the existing implementations.

TextReader defaults to BOM detection, then the existing Russian ANSI/cp1251
profile without a BOM. TextWriter defaults to UTF-8, LF line splitter, CRLF
conversion and no BOM. **The fourth TextWriter stream argument is a string
conversion splitter, not the file overload's Boolean AppendWriting.** File
constructors and Open signatures retain their existing behavior.

JSONReader defaults to UTF-8; its encoding may be a string or TextEncoding.
JSONWriter's encoding is a string, defaults to UTF-8 and accepts an empty string
as UTF-8. Its BOM flag defaults to False. XMLWriter defaults to UTF-8 and BOM=True,
as explicitly stated in the Russian reference. An unspecified/empty XMLWriter
encoding does not add an encoding attribute to a written XML declaration.

XMLReader without an explicit encoding keeps the existing XML parser's detection
of BOM/declaration; an explicit string or TextEncoding uses the existing strict
text decoder. This resolves the reference's UTF-8-default versus auto-detection
wording as a documented local choice, not a new observation of platform priority.
Admitted codecs are the existing bounded UTF-8/UTF-16LE/UTF-16BE and legacy codec
subset in file_io. Unknown/stateful/exotic encodings and malformed substitution
are not silently delegated to arbitrary host codecs.

## Lifetime, position and publication profile

- Caller streams are borrowed, never implicitly closed by these wrappers.
  Writers flush them when closing their adapter; callers still own explicit
  stream Close and any eventual file cleanup.
- Readers snapshot from the current byte position to end on Open/construction.
  Successful attachment consumes that remainder, even before the first logical
  Read. Later reads walk the independent existing text/token snapshot. Native
  partial-read byte positions and concurrent modification visibility are not
  claimed. A decode/attachment budget error restores the logical stream cursor
  and leaves the reader's previous source intact.
- JSON/XML parsing remains lazy at the first Read. Malformed JSON/XML errors can
  therefore occur after successful attachment has consumed the byte remainder;
  this does not rewind the source. XML entity/DTD/network resolution remains
  forbidden in the existing parser.
- TextReader created with the stream constructor keeps Close as a no-op, exactly
  as stated by that constructor's RU/EN documentation. A later Open resets this
  constructor mode. Open(stream) on an existing reader uses ordinary reader
  Close to release the snapshot while leaving the stream open. This distinction
  is explicit because Open documentation does not repeat the constructor rule.
- TextWriter writes at the current position without truncating or appending
  implicitly. JSON/XML writers retain their existing bounded whole-document
  assembly and publish on Close, returning an empty string for stream mode.
  External repositioning before publication changes the destination position;
  callers must not interleave unrelated writes into an active document.
- Requested BOM bytes are written once at the writer's attachment/publication
  position, even if nonzero; no existing prefix is inspected or normalized.
  This is a local rule. Native BOM treatment in reused streams is deferred.
- Existing JSON incomplete-container Close remains repairable. Existing XML
  output-target Close is terminal even if the document is incomplete. Ordinary
  errors remain catchable in BSL. Borrowed streams stay open on these failures.

The reference does not specify JSON/XML stream Close ownership/return values,
TextWriter stream ownership or precise flush/read-ahead. Borrowed lifetime and
empty stream-writer Close result are deliberate local choices. Full native
parity is not claimed for those details.

## Integrity and resource limits

The shared adapter admits exact built-in BSL stream types, checks access and
remaining byte bounds before allocating a snapshot, and uses the existing
stream write checks. A read-only memory view remains non-writable despite its
native-derived CanWrite property quirk. Closed owners, fixed-buffer capacity,
byte budgets and dynamically read-only backing buffers remain enforced.

No existing byte/text/node/depth caps were increased: streams and text snapshots
remain limited to 16 MiB, JSON/XML writers to their existing text budgets, and
parsers retain their existing node/depth limits. Encoding and capacity failures
are detected before a memory-stream write. An OS error can still cause partial
physical file I/O; no transactional disk-write guarantee is made.

## BSL examples

JSON can be exchanged without an intermediate file. All existing supported
ReadJSON/WriteJSON date, reviver and converter arguments remain available.

```bsl
Stream = New MemoryStream;
Writer = New JSONWriter;
Writer.OpenStream(Stream);
WriteJSON(Writer, New Structure("Code,Name", 42, "Пример"));
Writer.Close();
Stream.Seek(0, PositionInStream.Begin);
Reader = New JSONReader;
Reader.OpenStream(Stream);
Value = ReadJSON(Reader);
Reader.Close();
Stream.Close();
```

The same stream can carry a binary header followed by JSON, XML or text, using
its current position and the existing DataReader/DataWriter objects. Explicitly
finish each wrapper before attaching the next one. For text, specify UTF-8 on
reading when the writer emitted its default UTF-8 without a BOM:

```bsl
Stream = New MemoryStream;
Writer = New TextWriter(Stream);
Writer.WriteLine("Привет");
Writer.Close();
Stream.Seek(0, PositionInStream.Begin);
Reader = New TextReader(Stream, "UTF-8");
Line = Reader.ReadLine();
Reader.Close(); // stream constructor documents this as a no-op
Stream.Close();
```

## Official references and evidence limits

Official EDT 2026.2 archive:
https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar
SHA-256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
The archive is reference material, not redistributed here. Relevant RU/EN
members start with `nl/{ru,en}/html/SyntaxHelperContext/objects/catalog63/`:

- catalog598/TextReader/ctors/ctor262.html; methods/Open1422.html, Close1423.html.
- catalog598/TextWriter/ctors/ctor263.html; methods/Open1426.html, Close1427.html.
- catalog2298/JSONReader/methods/OpenStream5210.html, Close4902.html.
- catalog2298/JSONWriter/methods/OpenStream5211.html, Close4896.html.
- catalog565/XMLReader/methods/OpenStream5212.html, Close1538.html and XMLReader.html.
- catalog565/XMLWriter/methods/OpenStream5213.html, Close1546.html.

Async/Begin methods, nonseekable or foreign host streams, exact native buffering,
full encoding precedence, stream ownership calibration and exotic codec support
remain deferred. Native integration sources, immutable fixtures and acceptance
rules are unchanged by this implementation.
