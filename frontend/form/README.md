# Local form renderer

Dependency-free optional browser client for `yadinassi-form-ui/0`. It does not
execute BSL, implement server semantics, or open databases. The host owns form
state, revisions, lifecycle and all handlers. This is a bounded local adapter,
not native 1C managed-form parity.

## Build and focused checks

Requires Node 20 or newer. No `npm install`, external registry or CDN is needed.

```sh
cd frontend/form
npm run build
npm test
```

The closed deterministic build combines the three authored modules, copies HTML,
CSS and the project's MIT license, and hashes all production inputs/outputs into
`yadinassi/ui/assets/form/build-manifest.json`. Only `app.js`, `index.html`,
`style.css`, `LICENSE.txt` and `build-manifest.json` are packaged. Runtime serving
must keep the same closed local asset allowlist and security headers as catalog.
Tests cover the protocol, renderer/controller with a minimal DOM contract double,
and generated assets. They are not a substitute for a real-browser or native 1C
integration run.

## Interaction and recovery

- String, Boolean and Decimal fields dispatch tagged values. Decimal coefficient
  text never goes through JavaScript floating-point conversion. The small bounded
  exponent is used only to produce the codec's canonical Decimal spelling.
- Text changes apply on blur or Enter. Moving to a command or Close suppresses the
  racing blur request. The action validates all drafts, flushes changes in order,
  then dispatches its command at the returned revision. Repeated clicks are gated
  synchronously. Any failed field stops the remaining sequence.
- Valid error envelopes replace the state before showing a finite diagnostic;
  effects completed before a handler failure remain visible. A submitted field
  adopts the authoritative value, including on stale-revision rejection. Other
  local drafts remain until accepted, removed, made read-only, or refreshed.
- Malformed responses, HTTP failures and network loss lock editing. Only an
  explicit **Refresh state** reads the authoritative snapshot; no event is retried.
  Refresh replaces unsubmitted local inputs. Host `uncertain`/`outcome_unknown`
  locks are permanent for that attached session, even if a later snapshot clears
  its flag. Reattaching with a different launch key starts a different session.
- A launch key is read from `#session=`, removed with `history.replaceState`, and
  kept only in memory. No form data, drafts or keys enter browser storage. After
  page reload, reopen the complete launcher URL. Reattaching uses `form.hello`,
  which the persistent bridge maps to a read-only snapshot after first attach.
- Date values show exact native 100-microsecond tick text and are read-only. There
  is no JavaScript Date conversion or timezone conversion. Null, Undefined and
  label views are also read-only. Date editing, references, tables, nested forms,
  file uploads and arbitrary browser/host commands are outside this profile.
- Rendering uses bounded text properties, never host HTML or dynamic code. Keyed
  controls retain identity; busy transitions restore focus and clamp the selection
  to a normalized value without stealing focus from another active element.
