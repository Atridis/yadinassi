"""Raw physical observations and guarded public mixed-card runtime comparison."""
from document_read_fixture import BLOCKS,load,validate_capture
from linked_card_packet.base import scalar_wire


def _fresh(rows,s):
    import uuid
    values=[]
    for row in rows[18:20]:
        if row['status']!='ok' or row['kind']!='string':return False
        text=''.join(chr(n) for n in row['value'])
        try:value=uuid.UUID(text)
        except (ValueError,AttributeError):return False
        if str(value)!=text or value.int==0:return False
        values.append(text)
    known={*s.base.metadata_ids,*s.base.record_ids,*s.product_rows,*s.attribute_ids}
    return (values[0]!=values[1] and not known.intersection(values)
        and all(row['status']=='ok' and row['kind']=='boolean' and row['value'] is True for row in rows[20:22]))


def compare(actual,native,s,block):
    left=scalar_wire.validate_output(actual);right=scalar_wire.validate_output(native)
    available=validate_capture(native,s,block)['availability']=='available'
    fresh=block=='identity'
    matched=[i for i,(a,b) in enumerate(zip(left,right),1) if a==b and not(fresh and i in (19,20))]
    relations=dict(actual=_fresh(left,s),native=_fresh(right,s)) if fresh else None
    if fresh and all(relations.values()):matched=sorted([*matched,19,20])
    missing=[i for i in range(1,25) if i not in matched]
    # Each fresh UUID remains untouched in outputs. Its relational assessment,
    # not byte equality across independent sessions, supplies only these two IDs.
    return dict(mode='deterministic_with_fresh_relations' if fresh else 'deterministic',
        matched=not missing and available,matched_ids=matched,mismatched_ids=missing,
        fresh_relations=relations)


def execute(database,s):
    from yadinassi import Interpreter
    from yadinassi.database_context import FileDBContext
    from yadinassi.native_targets import LINUX_8_3_27_1508
    files=next(files for repeat in (1,2) for setup,_,files in (load(repeat),) if setup==s)
    output={}
    for block in BLOCKS:
        lines=[];interpreter=Interpreter(output=lines.append,database_context=FileDBContext(database),native_target=LINUX_8_3_27_1508)
        try:interpreter.execute(files[block+'.bsl'].decode('utf-8'),source='document-read-'+block+'.bsl')
        finally:interpreter.close()
        raw=('\n'.join(lines)+'\n').encode('ascii');validate_capture(raw,s,block);output[block]=raw.decode('ascii')
    return output


def readback(read_at,size,database,s,native,mapping):
    from document_read_physical import observe
    _,manifest,_=next(x for repeat in (1,2) for x in (load(repeat),) if x[0]==s)
    physical=observe(read_at,size,manifest['profile'],mapping)
    actual=execute(database,s)
    comparisons={block:compare(actual[block].encode('ascii'),native[block].encode('ascii'),s,block) for block in BLOCKS}
    return dict(physical=physical,outputs=actual,comparison=comparisons)
