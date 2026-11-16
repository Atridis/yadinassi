import sys,json,subprocess
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
out={'commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'cases':{}}
for case in ('nested_visit','invalid_target','omitted_operand'):
 vm=Interpreter(execution_backend='compiled-strict');seen=[];vm.register_function('Host',lambda:seen.append(1))
 try:
  if case=='nested_visit':
   p=parse('If True Then x=1;y=2;EndIf;');vm._compiled().prepare(p);vm.visit(p[0].branches[0][1][0])
  else:
   p=parse('Host();x=1;')
   if case=='invalid_target':p[1].target=p[1].value
   else:p[1].value=ast.OmittedArgument(p[1].token)
   vm.execute_program(p)
  result={'status':'ok','x':str(vm.variables.get('x'))}
 except Exception as error:result={'status':type(error).__name__,'reason':str(error)}
 result['host_effects']=len(seen);out['cases'][case]=result;vm.close()
print(json.dumps(out))
