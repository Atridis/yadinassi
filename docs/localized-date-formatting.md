# Localized date Format work in progress

This branch extends the existing bounded date formatter, not the interpreter.
The target is one coherent standalone Russian profile: documented DF/ДФ tokens,
month/day names, quarter/year forms and DLF/ДЛФ date/time styles, integrated with
DE/ДП and the existing parameter scanner and 4096 UTF-16 text/output limits.
Other locales and a live infobase's regional settings are outside the profile.

The initial implementation separates deterministic calendar rendering into
`date_formatting.py`. Russian numeric aliases, y/q, full month names and the
five local styles follow the official examples. Textual spellings, twelve-hour
behavior and competing DF/DLF selection still need finite native acquisition;
unsupported combinations remain explicit errors rather than guessed precedence.
This checkpoint is not a completed compatibility claim.

Source: EDT 2026.2 archive
https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar
SHA-256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
`nl/{ru,en}/html/SyntaxHelperContext/objects/Global_context/methods/catalog20/Format971.html`.
The old original40/supplement56 `MMMM` observation already establishes the
standalone spelling `Октябрь`; official compound examples use `20 августа` and
`20 ноября 2005 г. 14:03:23`. Existing native sources and captures remain immutable.
