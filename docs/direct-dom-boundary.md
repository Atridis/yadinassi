# Direct DOM wiring

This follow-up connects existing DOMBuilder, DOMWriter, DOMDocument and namespace
resolver constructors, exact node/list/XPath receiver classes and DOMNodeType to
the ordinary direct boundary. It introduces no new parsing or execution engine.
List indexing/iteration uses the finite canonical DOM list API. DOM document
ownership, hierarchy, graph work limits and transactional writer preflight remain
in their existing implementations. No additional file authority is introduced:
DOM readers/writers consume exact existing XMLReader/XMLWriter handles.

Two argument type checks now use class identity instead of equality, so a foreign
Python metaclass cannot run while rejecting a node or numeric list index.
Missing constructor registration stays a catchable unknown-type error; replaced
implementations remain an authority denial. Private attributes remain unavailable.

Of the 22 original Linux XMLReader failures, the combined XML/DOM changes recover
19. Three remaining DOM comparison/acquisition tests reveal a distinct existing
string-concatenation issue: missing GetAttribute returns Undefined, and the direct
compiler emits Python str + None rather than BSL string conversion. Case19 is
left failing without changing DOM.GetAttribute, native captures or expected data.
The twelve native XPath replay cases all pass. XMLStringProcessing, MemoryStream
constructor admission and the scalar concatenation issue remain outside scope.

Source-owned applications retain their previous narrow XML/XDTO policy. The new
standalone settings/DOM constructors are explicitly denied in SourceBoundary;
its existing reader/writer construction still takes the owning XML adapter.

Source-created XML handles carry weak private provenance (no contents scan and no
strong owner retention). Plain XML methods and DOM reader/writer arguments reject
these handles, including after the source application closes. This prevents a
retained source handle from gaining standalone file/general XML operations.
