"""Raw physical observations and guarded public mixed-card runtime comparison."""
from linked_card_fixture import BLOCKS,load,validate_capture
from linked_card_packet.base import scalar_wire


def compare(actual,native,s,block):
    left=scalar_wire.validate_output(actual);right=scalar_wire.validate_output(native)
    matched=[i for i,(a,b) in enumerate(zip(left,right),1) if a==b]
    missing=[i for i in range(1,25) if i not in matched]
    available=validate_capture(native,s,block)['availability']=='available'
    return dict(mode='deterministic',matched=not missing and available,
        matched_ids=matched,mismatched_ids=missing)


def execute(database,s):
    from yadinassi import Interpreter
    from yadinassi.database_context import FileDBContext
    from yadinassi.native_targets import LINUX_8_3_27_1508
    files=next(files for repeat in (1,2) for setup,_,files in (load(repeat),) if setup==s)
    output={}
    for block in BLOCKS:
        lines=[];interpreter=Interpreter(output=lines.append,database_context=FileDBContext(database),native_target=LINUX_8_3_27_1508)
        try:interpreter.execute(files[block+'.bsl'].decode('utf-8'),source='linked-card-'+block+'.bsl')
        finally:interpreter.close()
        raw=('\n'.join(lines)+'\n').encode('ascii');validate_capture(raw,s,block);output[block]=raw.decode('ascii')
    return output


def readback(read_at,size,database,s,native,mapping):
    from linked_card_physical import observe
    _,manifest,_=next(x for repeat in (1,2) for x in (load(repeat),) if x[0]==s)
    physical=observe(read_at,size,manifest['schema'],mapping)
    actual=execute(database,s)
    comparisons={block:compare(actual[block].encode('ascii'),native[block].encode('ascii'),s,block) for block in BLOCKS}
    return dict(physical=physical,outputs=actual,comparison=comparisons)
