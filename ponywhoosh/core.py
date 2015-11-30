#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: d555

from collections import defaultdict
import os
import re
import sys

from pony import orm
from pony.orm.serialization import to_dict
from index import Index as PonyWhooshIndex
from whoosh import fields as whoosh_module_fields
from whoosh import index as whoosh_module_index
from whoosh import qparser
import whoosh

from pprint import pprint

basedir = os.path.abspath(os.path.dirname(__file__))

__all__ = ['PonyWhoosh']


class PonyWhoosh(object):

    """A top level class that allows to register indexes.

    Attributes:
        * DEBUG (bool): Description
        * indexes_path (str): this is the name where the folder of the indexes are going to be stored.
        * route (TYPE): This config let you set the route for the url to run the html template.
        * search_string_min_len (int): This item let you config the minimun string value possible to perform search.
        * template_path (TYPE): Is the path where the folder of templates will be store.
        * writer_timeout (int): Is the time when the writer should stop the searching.
    """

    indexes_path = 'indexes'
    writer_timeout = 2
    search_string_min_len = 2
    debug = False

    _indexes = {}
    _entities = {}

    def __init__(self):
        if not os.path.exists(self.indexes_path):
            os.makedirs(self.indexes_path)


    def delete_indexes(self):
        """This set to empty all the indixes registered.

        Returns:
            TYPE: This empty all the indexes.
        """
        self._indexes = {}

    def indexes(self):
        """Summary

        Returns:
            TYPE: This returns all the indexes items stored.
        """
        return [v for k, v in self._indexes.items()]

    def create_index(self, index):
        """Creates and opens index folder for given index.

        If the index already exists, it just opens it, otherwise it creates it first.

        Args:
            wh (TYPE): All the indexes stored.
        """

        index._path = os.path.join(self.indexes_path, index._name)

        if whoosh.index.exists_in(index._path):
            _whoosh = whoosh.index.open_dir(index._path)
        elif not os.path.exists(index._path):
            os.makedirs(index._path)
            _whoosh = whoosh.index.create_in(index._path, index._schema)
        index._whoosh = _whoosh

    def register_index(self, index):
        """
        Registers a given index:

        * Creates and opens an index for it (if it doesn't exist yet)
        * Sets some default values on it (unless they're already set)
        * Replaces query class of every index's model by PonyWhoosheeQuery

        Args:
            wh (TYPE): Description
        """

        self._indexes[index._name] = index
        self.create_index(index)
        return index

    def register_model(self, *fields, **kw):
        """Registers a single model for fulltext search. This basically creates
        a simple PonyWhooshIndex for the model and calls self.register_index on it.

        Args:
            *fields: all the fields indexed from the model. 
            **kw: The options for each field, sortedby, stored ... 
        """

        index = PonyWhooshIndex(pw=self)

        index._kw = kw
        index._fields = fields

        def inner(model):
            """This look for the types of each field registered in the index, whether if it is 
            Numeric, datetime or Boolean. 

            Args:
                model (TYPE): Description

            Returns:
                TYPE: Description
            """

            index._name = model._table_
            if not index._name:
                index._name  = model.__name__

            self._entities[index._name] = model

            index._schema_attrs = {}

            index._primary_key_is_composite =  model._pk_is_composite_
            index._primary_key = [f.name for f in model._pk_attrs_]
            index._primary_key_type = 'list'
            type_attribute = {} 

            for field in model._attrs_:
                if field.is_relation:
                    continue
                
                assert hasattr(field, "name") and hasattr(field, "py_type")
                
                fname = field.name
                if hasattr(field.name, "__name__"):
                    fname = field.name.__name__

                stored = kw.get("stored", False)
                if fname in index._primary_key:
                    kw["stored"] = True
                # we're not supporting this kind of data
                ftype = field.py_type.__name__
                if ftype in ['date', 'datetime', 'datetime.date']:
                    kw["stored"] = stored
                    continue

                fwhoosh = fwhoosh = whoosh.fields.TEXT(**kw)

                if field == model._pk_:
                    index._primary_key_type = ftype
                    fwhoosh = whoosh.fields.ID(stored=True, unique=True)

                if fname in index._fields:
                    if not field.is_string:
                        if ftype in ['int', 'float']:
                            fwhoosh = whoosh.fields.NUMERIC(**kw)
                        elif ftype == 'bool':
                            fwhoosh = whoosh.fields.BOOLEAN(stored=True)

                type_attribute[fname] = ftype
                index._schema_attrs[fname] = fwhoosh
                kw["stored"] = stored

            index._schema = whoosh.fields.Schema(**index._schema_attrs)

            self.register_index(index)

            def _middle_save_(obj, status):
                """Summary

                Args:
                    obj (TYPE): Description
                    status (TYPE): Description

                Returns:
                    TYPE: Description
                """
                writer = index._whoosh.writer(timeout=self.writer_timeout)

                dict_obj = obj.to_dict()

                def dumps(v):
                    if isinstance(v, int):
                        return unicode(v)
                    if isinstance(v, float):
                        return '%.9f' % v
                    return unicode(v)

                attrs = {k: dumps(v) for k, v in dict_obj.iteritems() if k in index._schema_attrs.keys()}

                if status == 'inserted':
                    writer.add_document(**attrs)
                elif status == 'updated':
                    writer.update_document(**attrs)
                elif status in set(['marked_to_delete', 'deleted', 'cancelled']):
                    writer.delete_by_term(primary, attrs[primary])

                writer.commit()
                return obj._after_save_

            model._after_save_ = _middle_save_
            model._pw_index_ = index
            index._model = model
            return model
        return inner

    @orm.db_session
    def search(self, *arg, **kw):
        """Search function. This allows you to search using the following arguments.

        Args:
            *arg: The search string. 
            **kw: The options available for searching: include_entity, add_wildcards, something, 
            fields, except_fields, etc. These options were described previously. 

        Returns:
            TYPE: Description
        """
        output = {
            'runtime': 0,
            'results': {},
            'matched_terms': defaultdict(set),
            'cant_results': 0
        }

        indexes = self.indexes()

        models = kw.get('models', self._entities.values())
        models = [self._entities.get(model, None) if isinstance(model, str) or isinstance(model, unicode)
                  else model for model in models]
        models = filter(lambda x: x is not None, models)

        if models == [] or not models:
            models = self._entities.values()

        if self.debug:
            print "SEARCHING ON MODELS -> ", models

        indexes = [m._pw_index_ for m in models if hasattr(m, '_pw_index_')]

        if indexes == []:
            return output

        runtime, cant = 0, 0

        ma = defaultdict(set)
        for index in indexes:
            res = index.search(*arg, **kw)
            runtime += res['runtime']
            cant += res['cant_results']
            if res['cant_results'] > 0:
                output['results'][index._name] = {
                    'items': res['results'],
                    'matched_terms': res['matched_terms']
                }
                for k, ts in res['matched_terms'].items():
                    for t in ts:
                        ma[k].add(t)

        output['runtime'] = runtime
        output['matched_terms'] = {k: list(v) for k, v in ma.items()}
        output['cant_results'] = cant
        return output
