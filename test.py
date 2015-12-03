#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: d555


import os
from pprint import pprint
from pprint import pprint
import shutil
import tempfile
from unittest import TestCase

from pony.orm import *
from ponywhoosh import PonyWhoosh, search, full_search


class BaseTestCases(object):

    class BaseTest(TestCase):

        def __init__(self, *args, **kwargs):
            super(BaseTestCases.BaseTest, self).__init__(*args, **kwargs)
            

        def setUp(self):
            self.pw = PonyWhoosh()
            self.pw.indexes_path = tempfile.mkdtemp()
            self.pw.debug = False

            self.db = Database()

            @self.pw.register_model('name', 'age', stored=True, sortable=True)
            class User(self.db.Entity):
                id = PrimaryKey(int, auto=True)
                name = Required(unicode)
                age = Optional(int)
                attributes = Set('Attribute')

            @self.pw.register_model('weight', 'sport', 'name', stored=True, sortable=True)
            class Attribute(self.db.Entity):
                id = PrimaryKey(int, auto=True)
                name = Optional(unicode)
                user = Optional("User")
                weight = Required(unicode)
                sport = Optional(unicode)

            self.db.bind('sqlite', ':memory:', create_db=True)
            self.db.generate_mapping(create_tables=True)
            self.User = User
            self.Attribute = Attribute

        @db_session
        def fixtures(self):
            self.u1 = self.User(name=u'jonathan', age=u'15')
            self.u2 = self.User(name=u'felipe', age=u'19')
            self.u3 = self.User(name=u'harol', age=u'16')
            self.u4 = self.User(name=u'felun', age=u'16')
            self.a1 = self.Attribute(name=u'felun', user=self.u1, weight=u'80', sport=u'tejo')
            self.a2 = self.Attribute(name=u'galun', user=self.u2, weight=u'75', sport=u'lucha de felinas')
            self.a3 = self.Attribute(name=u'ejote', user=self.u3, weight=u'65', sport=u'futbol shaulin')

        def tearDown(self):
            shutil.rmtree(self.pw.indexes_path, ignore_errors=True)
            self.pw.delete_indexes()
            self.db.drop_all_tables(with_all_data=True)

        def test_search(self):
            self.fixtures()
            found = self.User._pw_index_.search('harol', include_entity=True)
            self.assertEqual(found['cant_results'], 1)
            self.assertEqual(self.u3.id, found['results'][0]['entity']['id'])

        def test_search_something(self):
            self.fixtures()
            found = self.User._pw_index_.search('har', something=True, include_entity=True)
            self.assertEqual(found['cant_results'], 1)

        def test_search_sortedby(self):
            self.fixtures()
            found = self.Attribute._pw_index_.search('lun', add_wildcards=True, sortedby="weight", include_entity=True)
            self.assertEqual(self.a2.id, found['results'][0]['entity']['id'])
            self.assertEqual(self.a1.id, found['results'][1]['entity']['id'])

        def test_full_search_without_wildcards(self):
            self.fixtures()

            found = full_search(self.pw, "fel")
            self.assertEqual(found['cant_results'], 0)

        def test_full_search_with_wildcards(self):
            self.fixtures()

            found = full_search(self.pw, "fel", add_wildcards=True, include_entity=True)
            self.assertEqual(found['cant_results'], 4)

        def test_fields(self):
            self.fixtures()
            results = full_search(self.pw, "felun", include_entity=True, fields=["name"])
            self.assertEqual(results['cant_results'], 2)

        def test_models(self):
            self.fixtures()
            results = full_search(self.pw, "felun", include_entity=True, models=['User'])
            self.assertEqual(results['cant_results'], 1)

        def test_except_field(self):
            self.fixtures()
            results = full_search(self.pw, "felun", except_fields=["name"])
            self.assertEqual(results['cant_results'], 0)


class TestGeneral(BaseTestCases.BaseTest):

    def setUp(self):
        super(TestGeneral, self).setUp()
