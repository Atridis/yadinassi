"""Unmodified public runtime probes plus measurement-only physical observations."""
import hashlib
from catalog_read_fixture import BLOCKS, validate_capture
from catalog_read_packet import scalar_wire, probe


def compare(actual, native, b, block):
    left = scalar_wire.validate_output(actual, case_count=12 if block == 'fresh' else 24)
    right = scalar_wire.validate_output(native, case_count=12 if block == 'fresh' else 24)
    if block == 'fresh':
        # Raw freshly generated UUID strings stay in both wires; equality is
        # intentionally not a parity requirement for independent executions.
        a = probe.assess_fresh(actual, b.setup); n = probe.assess_fresh(native, b.setup)
        return dict(mode='fresh_relations', matched=bool(a['accepted'] and n['accepted']),
                    matched_ids=[], mismatched_ids=[])
    matched = [i for i, (a, n) in enumerate(zip(left, right), 1) if a == n]
    missing = [i for i in range(1, 25) if i not in matched]
    availability = validate_capture(native, b, block)['availability']
    return dict(mode='deterministic', matched=not missing and availability == 'available',
                matched_ids=matched, mismatched_ids=missing)


def execute(database, b):
    from yadinassi import Interpreter
    from yadinassi.database_context import FileDBContext
    from yadinassi.native_targets import LINUX_8_3_27_1508
    from catalog_read_fixture import load
    # The saved names uniquely select the source-bound fixture, never caller BSL.
    files = next(files for repeat in (1, 2) for fixture, _, files in (load(repeat),) if fixture == b)
    output = {}
    for block in BLOCKS:
        lines = []
        interpreter = Interpreter(output=lines.append, database_context=FileDBContext(database),
                                  native_target=LINUX_8_3_27_1508)
        try:
            interpreter.execute(files[block+'.bsl'].decode('utf-8'), source='catalog-read-'+block+'.bsl')
        finally:
            interpreter.close()
        raw = ('\n'.join(lines)+'\n').encode('ascii')
        validate_capture(raw, b, block)
        output[block] = raw.decode('ascii')
    return output


def readback(read_at, size, database, b, native):
    from catalog_read_physical import observe
    physical = observe(read_at, size, b)
    actual = execute(database, b)
    comparison = {block:compare(actual[block].encode('ascii'), native[block].encode('ascii'), b, block)
                  for block in BLOCKS}
    return dict(physical=physical, outputs=actual, comparison=comparison)
