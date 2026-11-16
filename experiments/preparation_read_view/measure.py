"""Paired actual SQLite informational preparation, old/new method, same checkout."""
import json, statistics, subprocess, time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
import test_product_form_events as fixture
from yadinassi.python_direct_form_events import ProductEventBoundary

old_namespace={'__name__':'yadinassi._baseline_form_events','__package__':'yadinassi'}
# Dataclass compilation needs a real module; compile only the original class method.
import ast
source=subprocess.check_output(['git','show','7e2d5123:yadinassi/python_direct_form_events.py'],text=True)
module=ast.parse(source)
method=next(n for c in module.body if isinstance(c,ast.ClassDef) and c.name=='ProductEventBoundary' for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_object')
import yadinassi.python_direct_form_events as direct
old_namespace.update(vars(direct))
exec(compile(ast.Module(body=[method],type_ignores=[]),'<baseline>','exec'),old_namespace)
old=old_namespace['prepare_object'];new=ProductEventBoundary.prepare_object
result={}
for count in (1,32):
    f=fixture.ProductFormEventTests();f.setUp()
    try:
        for i in range(1,count):
            f.vm.execute(f'W=Справочники.Склады.СоздатьЭлемент(); W.Код="{i+1}"; W.Наименование="Warehouse {i}"; W.Записать(); R=Карточка.Склады.Добавить(); R.Склад=W.Ссылка;')
        for method in (old,new):
            ProductEventBoundary.prepare_object=method
            assert not f.run_event('BeforeWriteAtServer').cancel
        samples={'before':[],'after':[]}
        for trial in range(7):
            for label,method in ((('before',old),('after',new)) if trial%2==0 else (('after',new),('before',old))):
                ProductEventBoundary.prepare_object=method
                start=time.perf_counter();out=f.run_event('BeforeWriteAtServer');elapsed=(time.perf_counter()-start)*1000
                assert not out.cancel and not out.messages
                assert f.context.backend._active is None
                samples[label].append(elapsed)
        result[str(count)]={'samples_ms':samples,'median_ms':{k:statistics.median(v) for k,v in samples.items()}}
    finally:
        ProductEventBoundary.prepare_object=new;f.doCleanups()
print(json.dumps(result,indent=2))
