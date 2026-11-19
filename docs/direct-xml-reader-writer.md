# Direct XML reader and writer

Plain direct execution admits the existing exact XMLReader, XMLWriter and their
settings classes, namespace context and XML enum singletons. It uses their finite
BSL member protocols, not Python reflection or a fallback interpreter. Optional
argument positions follow the existing reader/writer protocols; procedure-value
calls and missing required arguments fail before argument evaluation.

The canonical parser/writer remain unchanged: XML 1.0 validation, size/depth/node
limits, DTD/entity refusal, descriptor cleanup and external-file access checks
still apply. Source-owned XML/XDTO continues through its separate owning adapter.
Missing XML constructor registration is a catchable unknown-type error; replaced
factories remain an authority failure.

Of the exact 22 Linux CI tests formerly stopped at XMLReader construction, four
now pass. The other 18 advance to unsupported DOMBuilder, a distinct family.
The XML-only Reader/Writer/native-observation cohort plus new boundary tests has
46 tests. No native captures, fixtures, expected outputs or test skips changed.
MemoryStream constructors and XMLStringProcessing are outside this slice.
