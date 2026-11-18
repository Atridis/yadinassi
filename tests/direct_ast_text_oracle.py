"""Temporary differential oracle. Never used by production dispatch."""
from yadinassi.python_direct import REPAIRS, _reject, _owned_import_child
from yadinassi.syntax import ast

def compile_module(vm,program,nodes,source_text,source_name,*,_exports=False):
    from yadinassi.experimental_naked_collections import prepare,UnsupportedNakedSyntax
    from yadinassi.python_direct_database import NAMES as DATABASE_NAMES
    from yadinassi.python_direct_services import CONSTRUCTORS
    from yadinassi.python_direct_value_tree import CONSTRUCTOR_NAMES as TREE_NAMES
    from yadinassi.python_direct_names import NAMES as SYSTEM_NAMES
    from yadinassi.python_direct_imports import import_names
    imported=import_names(vm,program)
    program=[node for node in program if type(node) not in (ast.ServerInitializer,ast.Import)
             and (type(node) not in (ast.Var,ast.Routine) or (node.execution_context=='client' and not getattr(node,'is_dual',False)))]
    source_name=source_name or (nodes[0].token.source if nodes else '<строка>')
    if source_text is None:
        lines={node.token.line:node.token.source_line for node in nodes if node.token is not None}
        source_text='\n'.join(lines.get(line,'') for line in range(1,max(lines,default=0)+1))
    try:
        plan=prepare(source_text,source_name=source_name,repairs=REPAIRS,
                     module_names=tuple(vm.module_names),
                     constructors=TREE_NAMES+tuple(CONSTRUCTORS) + ("uuid","уникальныйидентификатор") + (("query","запрос") if vm.database_context is not None else ()),
                     external_names=tuple(SYSTEM_NAMES) + (DATABASE_NAMES if vm.database_context is not None else ()) + imported,
                     _import_names=imported,_dynamic_new=True,_collection_regions=True,_host_routine_bindings=bool(imported) or _owned_import_child(vm),parsed_ast=program,_trusted_entry=True,_return_last_expression=not _exports,
                     _export_routines=_exports,_initialize_module=not _exports,_persistent_routines=not _exports and any(type(node) is ast.Routine for node in program))
    except UnsupportedNakedSyntax as error:
        _reject(str(error))
    return plan

