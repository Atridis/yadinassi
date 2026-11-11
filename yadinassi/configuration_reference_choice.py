"""One server-owned reference choice for a declared configuration form.

No browser record UUID, callback, target name or reader is accepted. Scans are
fresh and bounded; overflow is explicit, not an incomplete result advertised
as complete. This is host functionality, not native choice-event parity.
"""
from copy import deepcopy
from secrets import token_hex
from uuid import UUID

from .catalog_backend import (BackendError, CatalogComparison, CatalogPredicate,
    CatalogOrder, CatalogScanRequest, CatalogValuePage, CatalogValueRow, CatalogKey)
from .form_model import BSLFormField, BSLFormTable
from .form_references import is_reference
from .form_replication import _pack_state
from .form_tables import validate_table_data
from .ui.protocol import encode_line


class ConfigurationReferenceChoice:
    def __init__(self, definition, server, owned):
        self.definition, self.server, self.owned = definition, server, owned
        self.pending = None
        self.changed_control = None
        self.uncertain = False
        self._ticket = None
        self._projection = None
        self._choices = {}
        self._issued = 0

    @property
    def active(self):
        return self._ticket is not None

    def projection(self):
        return deepcopy(self._projection)

    @staticmethod
    def _keys(action, expected):
        if type(action) is not dict or set(action) != set(expected.split()):
            raise ValueError('invalid reference choice action')

    def _resolve(self, session, action):
        control, row, column = (action[k] for k in ('control','row','column'))
        if type(control) is not str or not control or len(control)>128:
            raise ValueError('declared reference control required')
        form=session.form; item=form.items._values.get(control.casefold())
        from .form_layout import effective_state
        visible, enabled, readonly = effective_state(item) if type(item) in (BSLFormField, BSLFormTable) else (False, False, True)
        if type(item) not in (BSLFormField,BSLFormTable) or not visible or not enabled or readonly:
            raise ValueError('reference control unavailable')
        slot=item.data_path.casefold()
        if type(item) is BSLFormField:
            if row is not None or column is not None: raise ValueError('reference field is not a table')
            attr=form._attributes.get(slot)
            if attr is None: raise ValueError('unknown reference field')
            kind=attr.value_type; holder=form; member=slot
        else:
            if type(row) is not int or not 1<=row<=4096 or type(column) is not str or len(column)>128:
                raise ValueError('exact reference row/column required')
            table=form._tables.get(slot)
            if table is None: raise ValueError('unknown reference table')
            holder=table._lookup_id(row)
            col=next((c for c in table.schema.columns if c.name.casefold()==column.casefold()),None)
            # Reference descriptors are client-readonly by construction; the
            # declared column flag separately controls host choice availability.
            if col is None or col.read_only: raise ValueError('reference column unavailable')
            kind=col.value_type; member=col.name.casefold(); column=col.name
        target=next((target for s,c,target in self.definition.reference_slots
            if s.casefold()==slot and c.casefold()==('' if column is None else column.casefold())),None)
        if not is_reference(kind) or kind.scope is not session.reference_scope or kind.target!=target:
            raise ValueError('unregistered reference target')
        return {'item':item,'holder':holder,'member':member,'kind':kind,'target':target,
            'control':item.name,'row':row,'column':column,'owner':self.owned.object,
            'value':holder._data[member]}

    def _current(self, session, token):
        if type(token) is not str or self._ticket is None or token!=self._ticket['token']:
            raise ValueError('retired reference choice ticket')
        ticket=self._ticket
        now=self._resolve(session,ticket)
        if (ticket['owner'] is not self.owned.object or now['item'] is not ticket['item']
                or now['holder'] is not ticket['holder'] or now['member']!=ticket['member']
                or now['target']!=ticket['target'] or now['value']!=ticket['value']):
            raise ValueError('reference owner or row changed')
        return now

    def _scan(self, session, target, code):
        manager=session._reference_managers[target]
        if type(code) is not str or len(code)>manager._schema.code_length:
            raise ValueError('bounded exact code required')
        predicate=CatalogComparison('deletion_mark','eq',False)
        if code: predicate=CatalogPredicate('and',(predicate,CatalogComparison('code','eq',code)))
        view=manager._view()
        try:
            page=view.scan_catalog_values(manager._schema.identity,
                CatalogScanRequest(predicate=predicate,order=(CatalogOrder('code'),),page_size=32),('code','description'))
            if type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows)>32:
                raise BackendError('integrity')
            if page.continuation is not None:
                if type(page.continuation) is not str or len(page.continuation)!=32: raise BackendError('integrity')
                return [],{},'too_many_matches'
            choices={};rows=[];seen=set()
            for record in page.rows:
                if (type(record) is not CatalogValueRow or type(record.key) is not CatalogKey
                    or record.key.database_id!=view.database_id or record.key.catalog_id!=manager._schema.identity
                    or type(record.key.record_id) is not UUID or not record.key.record_id.int or record.key in seen
                    or type(record.values) is not tuple or len(record.values)!=2
                    or any(type(v) is not str for v in record.values)
                    or len(record.values[0])>manager._schema.code_length
                    or len(record.values[1])>manager._schema.description_length): raise BackendError('integrity')
                seen.add(record.key); choice=token_hex(16);choices[choice]=record.key
                rows.append({'choice':choice,'code':record.values[0],'description':record.values[1]})
            return rows,choices,None
        finally: view.close()

    def _prepare_install(self, session, destination, value):
        value=destination['kind'].adjust_value(value)
        holder=destination['holder'];member=destination['member'];old=holder._data
        prepared=dict(old);prepared[member]=value
        # Temporary detached dictionaries only, preserving row objects/IDs and
        # all other fields. Restore even on preflight failure, before return.
        try:
            holder._data=prepared
            validate_table_data(session.form)
            encode_line(_pack_state(session,self.server._handler_names))
        finally: holder._data=old
        return prepared,value

    def _install(self, session, destination, value):
        prepared,value=self._prepare_install(session,destination,value)
        if value==destination['value']: return False
        try: destination['holder']._data=prepared
        except BaseException:
            self.uncertain=True
            raise
        self.changed_control={k:destination[k] for k in ('control','row','column')}
        return True

    def execute(self, session):
        action=self.pending;self.pending=None;self.changed_control=None
        if (session is not self.server.session or session.closed or not session._busy
                or self.uncertain or self.owned.pending_commit or self.owned.pending_refresh):
            raise ValueError('idle owned reference form activation required')
        self.owned.verify_source()
        if type(action) is not dict or type(action.get('action')) is not str:
            raise ValueError('pending reference choice action required')
        mode=action['action']
        if mode in ('begin','clear'):
            self._keys(action,'action control row column')
            if self.active: raise ValueError('reference choice already active')
            destination=self._resolve(session,action)
            if mode=='clear':
                changed=self._install(session,destination,destination['kind'].adjust_value())
                return 'cleared' if changed else 'unchanged'
            if self._issued>=256: raise ValueError('reference choice limit')
            rows,choices,error=self._scan(session,destination['target'],'')
            token=token_hex(16);self._issued+=1
            projection={'ticket':token,'control':destination['control'],'row':destination['row'],
                'column':destination['column'],'title':session._reference_managers[destination['target']]._schema.name,
                'code':'','rows':rows,'error':error}
            encode_line(projection)
            self._ticket=dict(destination,token=token);self._choices=choices;self._projection=projection
            return 'opened'
        if mode=='filter':
            self._keys(action,'action ticket code');destination=self._current(session,action['ticket'])
            rows,choices,error=self._scan(session,destination['target'],action['code'])
            prospective=dict(self._projection,code=action['code'],rows=rows,error=error)
            encode_line(prospective);self._projection=prospective;self._choices=choices
            return 'filtered'
        if mode=='cancel':
            self._keys(action,'action ticket')
            if self._ticket is None or type(action['ticket']) is not str or action['ticket']!=self._ticket['token']:
                raise ValueError('retired reference choice ticket')
            self._ticket=self._projection=None;self._choices={}
            return 'cancelled'
        if mode=='apply':
            self._keys(action,'action ticket choice');destination=self._current(session,action['ticket'])
            if type(action['choice']) is not str or action['choice'] not in self._choices:
                raise ValueError('unknown choice identity')
            key=self._choices[action['choice']];manager=session._reference_managers[destination['target']]
            view=manager._view()
            try:
                card=view.read_catalog(key)
                if card is None or card.deletion_mark: raise BackendError('not_found')
            finally: view.close()
            changed=self._install(session,destination,manager._ref(key.record_id))
            self._ticket=self._projection=None;self._choices={}
            return 'applied' if changed else 'unchanged'
        raise ValueError('unknown reference choice action')
