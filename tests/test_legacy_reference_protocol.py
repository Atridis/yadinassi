import unittest
from yadinassi.ui.editor_protocol import validate_request
from yadinassi.ui.protocol import UIError

class LegacyReferenceProtocolTests(unittest.TestCase):
    def check(self,action):
        return validate_request({'jsonrpc':'2.0','id':1,'method':'editor.event','params':{'event':'referenceChoice','baseRevision':0,'action':action}})
    def test_begin_closed_destination_shapes(self):
        self.check({'action':'begin','control':'InputData1','section':None,'row':None})
        self.check({'action':'begin','control':None,'section':'Rows','row':'11111111-1111-1111-1111-111111111111'})
        for action in ({'action':'begin','control':None,'section':None,'row':None},{'action':'begin','control':'InputData1','section':'Rows','row':None},{'action':'begin','control':'x','section':None,'row':None,'extra':1}):
            with self.assertRaises(UIError):self.check(action)
    def test_opaque_actions_and_search_bounds(self):
        ticket='a'*32
        for kind in ['cancel','clear','refresh']:self.check({'action':kind,'ticket':ticket})
        self.check({'action':'apply','ticket':ticket,'choice':'b'*32})
        self.check({'action':'page','ticket':ticket,'cursor':'legacy-reference-page-'+'c'*32})
        self.check({'action':'search','ticket':ticket,'query':'needle'})
        for action in ({'action':'apply','ticket':ticket,'choice':'uuid'},{'action':'page','ticket':ticket,'cursor':None},{'action':'search','ticket':ticket,'query':'x'*129},{'action':'clear','ticket':ticket,'extra':False}):
            with self.assertRaises(UIError):self.check(action)
