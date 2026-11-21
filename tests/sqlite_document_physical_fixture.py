"""Raw in-memory/test-file witnesses for the owned relational document layout."""
from contextlib import closing
import sqlite3
from uuid import uuid4
from yadinassi.db.sqlite.sqlite_document_layout import data_table, section_table


def table_snapshot(connection, schema):
    tables = ('document_record',data_table(schema),
              *(section_table(schema,section) for section in schema.tabular_sections))
    return tuple(tuple(connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')) for table in tables)


def seed_document_headers(path, schema, count):
    with closing(sqlite3.connect(path)) as connection, connection:
        headers = connection.execute('SELECT * FROM document_record').fetchall()
        if len(headers) != 1: raise AssertionError('expected exactly one template document')
        document,record,revision,number,date,mark = headers[0]
        records = tuple((document,str(uuid4()),revision,str(i).zfill(len(number)),date,mark)
                        for i in range(2,count+1))
        connection.executemany('INSERT INTO document_record VALUES(?,?,?,?,?,?)',records)
        tables = ((data_table(schema),) if schema.fields else ()) + tuple(
            section_table(schema,section) for section in schema.tabular_sections)
        for table in tables:
            template = tuple(row[2:] for row in connection.execute(
                f'SELECT * FROM "{table}" WHERE document_id=? AND record_id=?',(document,record)))
            for row in template:
                connection.executemany(f'INSERT INTO "{table}" VALUES('+','.join('?' for _ in range(len(row)+2))+')',
                                       ((document,saved_record,*row) for _,saved_record,*_ in records))


def corrupt_part_order(sql, schema, number):
    table = section_table(schema,schema.tabular_sections[0])
    return sql(f'UPDATE "{table}" SET row_number=2 WHERE record_id=(SELECT record_id FROM document_record WHERE number=?)',(number,))


def remove_attributes(sql, schema, number):
    return sql(f'DELETE FROM "{data_table(schema)}" WHERE record_id=(SELECT record_id FROM document_record WHERE number=?)',(number,))
