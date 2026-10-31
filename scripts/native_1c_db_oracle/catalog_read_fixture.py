"""Saved identities and exact replay; no generation or caller-provided source."""
import hashlib
import json
from pathlib import Path
from catalog_read_packet import batch, probe
from protocol import require, unique

BLOCKS = ('identity', 'types', 'errors', 'fresh', 'cursor', 'fields', 'lookup', 'row4')
STATES = batch.STATES
ROOT = Path(__file__).with_name('catalog_read_packet')


def load(repeat):
    require(type(repeat) is int and repeat in (1, 2), 'invalid_input')
    root = ROOT / 'generated' / ('repeat-' + str(repeat))
    from inputs import read_source
    manifest = json.loads(read_source(root / 'manifest.json'), object_pairs_hook=unique)
    b = batch.Batch(probe.Setup(*(tuple(manifest[k]) for k in ('names', 'metadata_ids', 'record_ids'))),
                    tuple(manifest['extra_ids'])).validate()
    expected = {*(f'Catalogs/{n}.xml' for n in b.setup.names),
                *(n + '.bsl' for n in BLOCKS), *(f'setup-{s}.bsl' for s in STATES)}
    require(type(manifest['source_hashes']) is dict and set(manifest['source_hashes']) == expected, 'provenance_mismatch')
    files = {n: read_source(root / n) for n in sorted(expected)}
    require(all(hashlib.sha256(raw).hexdigest() == manifest['source_hashes'][n]
                for n, raw in files.items()), 'provenance_mismatch')
    fragments = {n: raw for n, raw in files.items() if n.endswith('.xml')}
    batch.validate_fragments(b, fragments, manifest['generated_ids'])
    require([list(row) for row in b.rows] == manifest['rows'], 'provenance_mismatch')
    for block in BLOCKS:
        rendered = (probe.render_fresh(b.setup) if block == 'fresh' else
                    probe.render(b.setup, block) if block in ('identity', 'types', 'errors') else
                    batch.render_block(b, block)[0])
        require(files[block + '.bsl'] == rendered.encode('utf-8'), 'provenance_mismatch')
    for state in STATES:
        require(files['setup-' + state + '.bsl'] == batch.render_setup(b, state).encode('utf-8'), 'provenance_mismatch')
    return b, manifest, files


def validate_capture(raw, b, block):
    """Keep unavailability distinct from malformed observers; no parity claim."""
    from catalog_read_packet import scalar_wire
    rows = scalar_wire.validate_output(raw, case_count=12 if block == 'fresh' else 24)
    require(not any(r['status'] == 'observer-error' for r in rows), 'invalid_marker')
    try:
        if block == 'fresh':
            result = probe.assess_fresh(raw, b.setup)
            return {'availability': 'available' if 'availability-control' not in result['reasons'] else 'unavailable',
                    'fresh_relations': result['accepted']}
        if block in ('identity', 'types', 'errors'): probe.require_available(raw, b.setup, block)
        else: batch.read_capture(raw, b)
    except ValueError as error:
        if str(error) != 'availability-control': raise
        return {'availability': 'unavailable', 'fresh_relations': None}
    return {'availability': 'available', 'fresh_relations': None}
