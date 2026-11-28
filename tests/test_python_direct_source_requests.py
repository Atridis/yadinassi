"""Direct request lifetime never calls the legacy scheduler executor."""
import unittest
from test_source_server_call import configuration
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.direct.source.python_direct_source_requests import request_scope
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class DirectSourceRequests(unittest.TestCase):
    def app(self,output=lambda value:None):
        app=SourceApplication(configuration(''),output=output)
        self.addCleanup(app.close);app.start();return app

    def test_root_cache_nested_sharing_and_restoration(self):
        vm=self.app().interpreter;context=vm._scheduler.active_context
        previous={'previous':1};context.request_cache=previous
        with request_scope(vm):
            cache=context.request_cache;self.assertIsNot(cache,previous)
            cache['key']=object()
            with request_scope(vm):
                self.assertIs(context.request_cache,cache)
                self.assertIn('key',cache)
            self.assertIn('key',cache)
        self.assertEqual(cache,{})
        self.assertIs(context.request_cache,previous)
        self.assertEqual(previous,{'previous':1})

    def test_failure_and_retarget_cleanup(self):
        vm=self.app().interpreter;context=vm._scheduler.active_context
        with self.assertRaisesRegex(ValueError,'failure'):
            with request_scope(vm):
                cache=context.request_cache;cache['key']=1
                raise ValueError('failure')
        self.assertEqual(cache,{})
        self.assertIsNone(context.request_cache)
        with self.assertRaises(BoundaryViolation):
            with request_scope(vm):
                cache=context.request_cache;cache['key']=1
                context.request_cache={}
        self.assertEqual(cache,{})
        self.assertIsNone(context.request_cache)

    def test_nested_foreign_app_has_independent_cache(self):
        first=self.app().interpreter;second=self.app().interpreter
        with request_scope(first):
            cache=first._scheduler.active_context.request_cache
            with request_scope(second):
                other=second._scheduler.active_context.request_cache
                self.assertIsNot(other,cache)
                self.assertIs(first._scheduler.active_context.request_cache,cache)
            self.assertIsNone(second._scheduler.active_context.request_cache)

    def test_actual_generated_nested_calls_share_one_request(self):
        seen=[];holder={}
        def emit(value):seen.append(holder['app'].interpreter._scheduler.active_context.request_cache)
        app=self.app(emit);holder['app']=app
        app.interpreter.execute('Function Inner() Message("inner"); Return 1; EndFunction\nMessage("root"); X=Inner();')
        self.assertEqual(len(seen),2);self.assertIs(seen[0],seen[1]);self.assertEqual(seen[0],{})
        app.interpreter.execute('Message("next");')
        self.assertIsNot(seen[0],seen[2]);self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)

    def test_actual_error_releases_request(self):
        seen=[];holder={}
        def emit(value):seen.append(holder['app'].interpreter._scheduler.active_context.request_cache)
        app=self.app(emit);holder['app']=app
        with self.assertRaises(Exception):app.interpreter.execute('Message("first"); Raise "fail";')
        self.assertEqual(seen[0],{});self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)
        app.interpreter.execute('Message("second");')
        self.assertIsNot(seen[0],seen[1])
