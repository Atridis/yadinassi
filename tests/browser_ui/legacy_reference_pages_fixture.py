"""Отдельная authored QA база: 70 вариантов подготовлены fixture, не через UI."""
import json
from pathlib import Path
import sys
from uuid import UUID
from yadinassi.catalog_backend import CatalogSchema, FieldSchema, CatalogDraft, CatalogKey, CatalogSelection, TabularSectionSchema
from yadinassi.configuration_xml import ConfigurationImport, ConfigurationFile
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

W, P, S, F, A = (UUID(int=i) for i in (62001,62002,63001,64001,64002))

def configuration():
    return ConfigurationImport(config_uuid=UUID(int=61001), name='OwnedLegacyReferencePages',activation_issues=(),
        catalogs=(CatalogSchema(W,'Warehouses',8,100),CatalogSchema(P,'Products',8,100,
            (FieldSchema(A,'DefaultWarehouse','catalog_ref',(),W),),
            (TabularSectionSchema(S,'Warehouses',(FieldSchema(F,'Warehouse','catalog_ref',(),W),)),))),
        files=(ConfigurationFile('Configuration.xml',b'<owned-legacy-reference-pages/>','xml'),),modules=())

def seed(root):
    backend=SQLiteCatalogBackend.create(root/'owned.sqlite',configuration())
    try:
        tx=backend.begin_write(UUID(int=66001))
        try:
            for i in range(70):
                tx.create(CatalogDraft(CatalogKey(backend.database_id,W,UUID(int=65000+i)),f'W{i:03}',f'Warehouse {i:03}',False,()))
            tx.commit()
        finally: tx.close()
    finally: backend.close()
    return {'seeded':True,'authoredReferenceRows':70,'productsInitially':0}

def audit(root):
    backend=SQLiteCatalogBackend(root/'owned.sqlite',read_only=True)
    try:
        view=backend.begin_read()
        try:
            warehouses=view.select_catalog(W,CatalogSelection(limit=71))
            products=view.select_catalog(P,CatalogSelection(limit=2))
            if len(warehouses)!=70 or len(products)!=1: raise ValueError('record_count')
            for row in warehouses:
                index=row.key.record_id.int-65000
                if not 0<=index<70 or (row.code,row.description,row.deletion_mark)!=(f'W{index:03}',f'Warehouse {index:03}',False): raise ValueError('seed_changed')
            product=products[0]
            if (product.code,product.description,product.deletion_mark)!=('PICKQA','Draft preserved after lost Apply',False): raise ValueError('product_values')
            if product.values!=(CatalogKey(view.database_id,W,UUID(int=65069)),): raise ValueError('scalar_reference')
            if len(product.tabular_sections)!=1 or product.tabular_sections[0].section_id!=S or len(product.tabular_sections[0].rows)!=1: raise ValueError('section_shape')
            row=product.tabular_sections[0].rows[0]
            if row.values!=(CatalogKey(view.database_id,W,UUID(int=65068)),): raise ValueError('section_reference')
            return {'warehouses':70,'products':1,'referenceRows':1,'productIdentity':str(product.key.record_id),'rowIdentity':str(row.identity),'revision':product.revision.token}
        finally: view.close()
    finally: backend.close()

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1] not in ('seed','audit'): raise SystemExit('invalid_arguments')
    root=Path(sys.argv[2])
    if not root.is_absolute() or not root.is_dir(): raise SystemExit('owned_directory_required')
    print(json.dumps(seed(root) if sys.argv[1]=='seed' else audit(root)))
