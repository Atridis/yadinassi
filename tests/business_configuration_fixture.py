"""Authored mixed business configuration, not native export evidence."""
from test_configuration_application_profile import application_sources
from document_form_fixture import sources as document_sources


def sources():
    files = application_sources()
    documents = document_sources()
    files.update({p: b for p, b in documents.items() if p.startswith('Documents/')})
    files['Configuration.xml'] = files['Configuration.xml'].replace(
        b'</ChildObjects>', b'<Document>Orders</Document></ChildObjects>')
    return files
