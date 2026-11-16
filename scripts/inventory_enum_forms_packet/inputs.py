"""Finite source dependencies for owned enum forms composition."""
EXTRA_FILES={}
for name in ('__init__.py', 'route.py', 'fixture.py', 'observe.bsl', 'Products.xml', 'Warehouses.xml', 'Receipt.xml', 'Issue.xml', 'Stock.xml', 'ReceiptModule.bsl', 'IssueModule.bsl', 'Units.xml', 'States.xml'):
    EXTRA_FILES["scripts/inventory_enum_behavior/"+name]="bootstrap/inventory_enum_behavior/"+name
for name in ('__init__.py', 'route.py', 'fixture.py', 'packet.py', 'Catalog.xml', 'SOURCE.json', 'generated/setup.json', 'generated/Catalog.xml', 'generated/observe.bsl'):
    EXTRA_FILES["scripts/catalog_object_behavior/"+name]="bootstrap/catalog_object_behavior/"+name
