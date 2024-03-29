##############################################################################
#
# Copyright (c) 2002 Zope Foundation and Contributors.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Date range index.
"""

import os
from datetime import datetime

from Globals import InitializeClass
from AccessControl.Permissions import manage_zcatalog_indexes
from AccessControl.Permissions import view
from AccessControl.SecurityInfo import ClassSecurityInfo
from Acquisition import aq_base
from Acquisition import aq_get
from Acquisition import aq_inner
from Acquisition import aq_parent
from App.Common import package_home
from App.special_dtml import DTMLFile
from BTrees.IIBTree import IITreeSet
from BTrees.IIBTree import difference
from BTrees.IIBTree import intersection
from BTrees.IIBTree import multiunion
from BTrees.IOBTree import IOBTree
from BTrees.Length import Length
from DateTime.DateTime import DateTime
from zope.interface import implements

from Products.PluginIndexes.common import safe_callable
from Products.PluginIndexes.common.UnIndex import UnIndex
from Products.PluginIndexes.common.util import parseIndexRequest
from Products.PluginIndexes.interfaces import IDateRangeIndex

_dtmldir = os.path.join(package_home(globals()), 'dtml')
MAX32 = int(2**31 - 1)


class RequestCache(dict):

    def __str__(self):
        return "<RequestCache %s items>" % len(self)


class DateRangeIndex(UnIndex):

    """Index for date ranges, such as the "effective-expiration" range in CMF.

    Any object may return None for either the start or the end date: for the
    start date, this should be the logical equivalent of "since the beginning
    of time"; for the end date, "until the end of time".

    Therefore, divide the space of indexed objects into four containers:

    - Objects which always match (i.e., they returned None for both);

    - Objects which match after a given time (i.e., they returned None for the
      end date);

    - Objects which match until a given time (i.e., they returned None for the
      start date);

    - Objects which match only during a specific interval.
    """
    implements(IDateRangeIndex)

    security = ClassSecurityInfo()

    meta_type = "DateRangeIndex"
    query_options = ('query', )

    manage_options= ({'label': 'Properties',
                      'action': 'manage_indexProperties'},
                    )

    since_field = until_field = None

    # int(DateTime('1000/1/1 0:00 GMT-12').millis() / 1000 / 60)
    floor_value = -510162480
    # int(DateTime('2499/12/31 0:00 GMT+12').millis() / 1000 / 60)
    ceiling_value = 278751600

    def __init__(self, id, since_field=None, until_field=None,
            caller=None, extra=None, floor_value=None, ceiling_value=None):

        if extra:
            since_field = extra.since_field
            until_field = extra.until_field
            floor_value = getattr(extra, 'floor_value', None)
            ceiling_value = getattr(extra, 'ceiling_value', None)

        self._setId(id)
        self._edit(since_field, until_field, floor_value, ceiling_value)
        self.clear()

    security.declareProtected(view, 'getSinceField')
    def getSinceField(self):
        """Get the name of the attribute indexed as start date.
        """
        return self._since_field

    security.declareProtected(view, 'getUntilField')
    def getUntilField(self):
        """Get the name of the attribute indexed as end date.
        """
        return self._until_field

    security.declareProtected(view, 'getFloorValue')
    def getFloorValue(self):
        """"""
        return self.floor_value

    security.declareProtected(view, 'getCeilingValue')
    def getCeilingValue(self):
        """"""
        return self.ceiling_value

    manage_indexProperties = DTMLFile('manageDateRangeIndex', _dtmldir)

    security.declareProtected(manage_zcatalog_indexes, 'manage_edit')
    def manage_edit(self, since_field, until_field, floor_value,
                    ceiling_value, REQUEST):
        """
        """
        self._edit(since_field, until_field, floor_value, ceiling_value)
        REQUEST['RESPONSE'].redirect('%s/manage_main'
                                     '?manage_tabs_message=Updated'
                                     % REQUEST.get('URL2'))

    security.declarePrivate('_edit')
    def _edit(self, since_field, until_field, floor_value=None,
              ceiling_value=None):
        """Update the fields used to compute the range.
        """
        self._since_field = since_field
        self._until_field = until_field
        if floor_value is not None:
            self.floor_value = int(floor_value)
        if ceiling_value is not None:
            self.ceiling_value = int(ceiling_value)

    security.declareProtected(manage_zcatalog_indexes, 'clear')
    def clear(self):
        """
            Start over fresh.
        """
        self._always = IITreeSet()
        self._since_only = IOBTree()
        self._until_only = IOBTree()
        self._since = IOBTree()
        self._until = IOBTree()
        self._unindex = IOBTree() # 'datum' will be a tuple of date ints
        self._length = Length()

    #
    #   PluggableIndexInterface implementation (XXX inherit assertions?)
    #
    def getEntryForObject(self, documentId, default=None):
        """
            Get all information contained for the specific object
            identified by 'documentId'.  Return 'default' if not found.
        """
        return self._unindex.get(documentId, default)

    def index_object(self, documentId, obj, threshold=None):
        """
            Index an object:

             - 'documentId' is the integer ID of the document

             - 'obj' is the object to be indexed

             - ignore threshold
        """
        if self._since_field is None:
            return 0

        since = getattr(obj, self._since_field, None)
        if safe_callable(since):
            since = since()
        since = self._convertDateTime(since)

        until = getattr(obj, self._until_field, None)
        if safe_callable(until):
            until = until()
        until = self._convertDateTime(until)

        datum = (since, until)

        old_datum = self._unindex.get(documentId, None)
        if datum == old_datum: # No change?  bail out!
            return 0

        if old_datum is not None:
            old_since, old_until = old_datum
            self._removeForwardIndexEntry(old_since, old_until, documentId)

        self._insertForwardIndexEntry(since, until, documentId)
        self._unindex[documentId] = datum

        return 1

    def unindex_object(self, documentId):
        """
            Remove the object corresponding to 'documentId' from the index.
        """
        datum = self._unindex.get(documentId, None)
        if datum is None:
            return

        since, until = datum
        self._removeForwardIndexEntry(since, until, documentId)
        del self._unindex[documentId]

    def uniqueValues(self, name=None, withLengths=0):
        """
            Return a list of unique values for 'name'.

            If 'withLengths' is true, return a sequence of tuples, in
            the form '(value, length)'.
        """
        if not name in (self._since_field, self._until_field):
            return []

        if name == self._since_field:
            t1 = self._since
            t2 = self._since_only
        else:
            t1 = self._until
            t2 = self._until_only

        result = []
        if not withLengths:
            result.extend(t1.keys())
            result.extend(t2.keys())
        else:
            for key in t1.keys():
                set = t1[key]
                if isinstance(set, int):
                    length = 1
                else:
                    length = len(set)
                result.append((key, length))
            for key in t2.keys():
                set = t2[key]
                if isinstance(set, int):
                    length = 1
                else:
                    length = len(set)
                result.append((key, length))
        return tuple(result)

    def _cache_key(self, catalog):
        cid = catalog.getId()
        counter = getattr(aq_base(catalog), 'getCounter', None)
        if counter is not None:
            return '%s_%s' % (cid, counter())
        return cid

    def _apply_index(self, request, resultset=None):
        """
            Apply the index to query parameters given in 'request', which
            should be a mapping object.

            If the request does not contain the needed parameters, then
            return None.

            Otherwise return two objects.  The first object is a ResultSet
            containing the record numbers of the matching records.  The
            second object is a tuple containing the names of all data fields
            used.
        """
        iid = self.id
        record = parseIndexRequest(request, iid, self.query_options)
        if record.keys is None:
            return None

        term = self._convertDateTime(record.keys[0])
        REQUEST = aq_get(self, 'REQUEST', None)
        if REQUEST is not None:
            catalog = aq_parent(aq_parent(aq_inner(self)))
            if catalog is not None:
                key = self._cache_key(catalog)
                cache = REQUEST.get(key, None)
                tid = isinstance(term, int) and term / 10 or 'None'
                if resultset is None:
                    cachekey = '_daterangeindex_%s_%s' % (iid, tid)
                else:
                    cachekey = '_daterangeindex_inverse_%s_%s' % (iid, tid)
                if cache is None:
                    cache = REQUEST[key] = RequestCache()
                else:
                    cached = cache.get(cachekey, None)
                    if cached is not None:
                        if resultset is None:
                            return (cached,
                                    (self._since_field, self._until_field))
                        else:
                            return (difference(resultset, cached),
                                    (self._since_field, self._until_field))

        if resultset is None:
            # Aggregate sets for each bucket separately, to avoid
            # large-small union penalties.
            until_only = multiunion(self._until_only.values(term))
            since_only = multiunion(self._since_only.values(None, term))
            until = multiunion(self._until.values(term))

            # Total result is bound by resultset
            if REQUEST is None:
                until = intersection(resultset, until)

            since = multiunion(self._since.values(None, term))
            bounded = intersection(until, since)

            # Merge from smallest to largest.
            result = multiunion([bounded, until_only, since_only,
                                 self._always])
            if REQUEST is not None and catalog is not None:
                cache[cachekey] = result

            return (result, (self._since_field, self._until_field))
        else:
            # Compute the inverse and subtract from res
            until_only = multiunion(self._until_only.values(None, term - 1))
            since_only = multiunion(self._since_only.values(term + 1))
            until = multiunion(self._until.values(None, term - 1))
            since = multiunion(self._since.values(term + 1))

            result = multiunion([until_only, since_only, until, since])
            if REQUEST is not None and catalog is not None:
                cache[cachekey] = result

            return (difference(resultset, result),
                    (self._since_field, self._until_field))

    def _insert_migrate(self, tree, key, value):
        treeset = tree.get(key, None)
        if treeset is None:
            tree[key] = IITreeSet((value, ))
        else:
            if isinstance(treeset, IITreeSet):
                treeset.insert(value)
            elif isinstance(treeset, int):
                tree[key] = IITreeSet((treeset, value))
            else:
                tree[key] = IITreeSet(treeset)
                tree[key].insert(value)

    def _insertForwardIndexEntry(self, since, until, documentId):
        """Insert 'documentId' into the appropriate set based on 'datum'.
        """
        if since is None and until is None:
            self._always.insert(documentId)
        elif since is None:
            self._insert_migrate(self._until_only, until, documentId)
        elif until is None:
            self._insert_migrate(self._since_only, since, documentId)
        else:
            self._insert_migrate(self._since, since, documentId)
            self._insert_migrate(self._until, until, documentId)

    def _remove_delete(self, tree, key, value):
        treeset = tree.get(key, None)
        if treeset is not None:
            if isinstance(treeset, int):
                del tree[key]
            else:
                treeset.remove(value)
                if not treeset:
                    del tree[key]

    def _removeForwardIndexEntry(self, since, until, documentId):
        """Remove 'documentId' from the appropriate set based on 'datum'.
        """
        if since is None and until is None:
            self._always.remove(documentId)
        elif since is None:
            self._remove_delete(self._until_only, until, documentId)
        elif until is None:
            self._remove_delete(self._since_only, since, documentId)
        else:
            self._remove_delete(self._since, since, documentId)
            self._remove_delete(self._until, until, documentId)

    def _convertDateTime(self, value):
        if value is None:
            return value
        if isinstance(value, (str, datetime)):
            dt_obj = DateTime(value)
            value = dt_obj.millis() / 1000 / 60 # flatten to minutes
        elif isinstance(value, DateTime):
            value = value.millis() / 1000 / 60 # flatten to minutes
        if value > MAX32 or value < -MAX32:
            # t_val must be integer fitting in the 32bit range
            raise OverflowError('%s is not within the range of dates allowed'
                                'by a DateRangeIndex' % value)
        value = int(value)
        # handle values outside our specified range
        if value > self.ceiling_value:
            return None
        elif value < self.floor_value:
            return None
        return value

InitializeClass(DateRangeIndex)

manage_addDateRangeIndexForm = DTMLFile('addDateRangeIndex', _dtmldir)


def manage_addDateRangeIndex(self, id, extra=None,
        REQUEST=None, RESPONSE=None, URL3=None):
    """
        Add a date range index to the catalog, using the incredibly icky
        double-indirection-which-hides-NOTHING.
    """
    return self.manage_addIndex(id, 'DateRangeIndex', extra,
        REQUEST, RESPONSE, URL3)
