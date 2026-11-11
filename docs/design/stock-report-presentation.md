# Saved-stock report presentation

Next planned UI block only. This does not amend the frozen #285 or #293 source.

- Render exact whole-second typed dates in a stable Gregorian date/time notation, without timezone conversion, floating-point date arithmetic, locale guesses or changing the value. Empty dates are explicit. A sub-second tick value remains visibly exact rather than rounded.
- Make generated column names easier to scan while retaining the exact source name visibly whenever a display label differs. Labels never become keys, reference choices, permissions or query inputs.
- Keep the report controls and page controls outside an explicitly labelled keyboard-focusable horizontal table viewport. Retain native scrolling, accessible column headers and unchanged snapshot/page fences.
- Preserve every wire shape, scalar validator, original form-editor limit, row/cell/page/input budget, source grant, backend snapshot, arithmetic and immutable ticket. Do not introduce exports, arbitrary sorting or new Query access.

Verification planned: pure JS date boundaries (year one/empty, leap/century, year 9999 maximum, exact fractional fallback), header identity/text safety, accessible viewport rendering and unchanged request/response semantics. Integrate with the next coherent UI block, not a standalone small PR; then run the existing stock/statement/preflight browser scenarios on that final tree.
