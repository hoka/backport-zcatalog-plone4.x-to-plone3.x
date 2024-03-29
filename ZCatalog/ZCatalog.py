##############################################################################
#
# Copyright (c) 2002 Zope Foundation and Contributors.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################
""" ZCatalog product
"""

import logging
import operator
import sys
import string
import time
import urllib

from Globals import InitializeClass
from AccessControl.Permission import name_trans
from AccessControl.Permissions import manage_zcatalog_entries
from AccessControl.Permissions import manage_zcatalog_indexes
from AccessControl.Permissions import search_zcatalog
from AccessControl.SecurityInfo import ClassSecurityInfo
from Acquisition import aq_base
from Acquisition import aq_parent
from Acquisition import Implicit
from App.Dialogs import MessageDialog
from App.special_dtml import DTMLFile
from DateTime.DateTime import DateTime
from DocumentTemplate.DT_Util import InstanceDict
from DocumentTemplate.DT_Util import TemplateDict
from DocumentTemplate.DT_Util import Eval
from AccessControl.DTML import RestrictedDTML
from OFS.Folder import Folder
from OFS.ObjectManager import ObjectManager
from Persistence import Persistent
from Products.PluginIndexes.interfaces import IPluggableIndex
import transaction
from ZODB.POSException import ConflictError
from zope.interface import implements

from Products.ZCatalog.Catalog import Catalog, CatalogError
from Products.ZCatalog.interfaces import IZCatalog
from Products.ZCatalog.ProgressHandler import ZLogHandler
from Products.ZCatalog.ZCatalogIndexes import ZCatalogIndexes
from plan import PriorityMap

LOG = logging.getLogger('Zope.ZCatalog')

manage_addZCatalogForm = DTMLFile('dtml/addZCatalog', globals())


def manage_addZCatalog(self, id, title, vocab_id=None, REQUEST=None):
    """Add a ZCatalog object. The vocab_id argument is ignored.
    """
    id = str(id)
    title = str(title)
    c = ZCatalog(id, title, container=self)
    self._setObject(id, c)
    if REQUEST is not None:
        return self.manage_main(self, REQUEST, update_menu=1)


class ZCatalog(Folder, Persistent, Implicit):
    """ZCatalog object

    A ZCatalog contains arbirary index like references to Zope
    objects.  ZCatalog's can index either 'Field' values of object, or
    'Text' values.

    ZCatalog does not store references to the objects themselves, but
    rather to a unique identifier that defines how to get to the
    object.  In Zope, this unique idenfier is the object's relative
    path to the ZCatalog (since two Zope object's cannot have the same
    URL, this is an excellent unique qualifier in Zope).

    Most of the dirty work is done in the _catalog object, which is an
    instance of the Catalog class.  An interesting feature of this
    class is that it is not Zope specific.  You can use it in any
    Python program to catalog objects.
    """

    implements(IZCatalog)

    security = ClassSecurityInfo()
    security.setPermissionDefault(manage_zcatalog_entries, ('Manager', ))
    security.setPermissionDefault(manage_zcatalog_indexes, ('Manager', ))
    security.setPermissionDefault(search_zcatalog, ('Anonymous', 'Manager'))
    security.declareProtected(search_zcatalog, 'all_meta_types')

    meta_type = "ZCatalog"
    icon = 'misc_/ZCatalog/ZCatalog.gif'

    manage_options = (
        {'label': 'Contents', 'action': 'manage_main'},
        {'label': 'Catalog', 'action': 'manage_catalogView'},
        {'label': 'Properties', 'action': 'manage_propertiesForm'},
        {'label': 'Indexes', 'action': 'manage_catalogIndexes'},
        {'label': 'Metadata', 'action': 'manage_catalogSchema'},
        {'label': 'Find Objects', 'action': 'manage_catalogFind'},
        {'label': 'Advanced', 'action': 'manage_catalogAdvanced'},
        {'label': 'Query Report', 'action': 'manage_catalogReport'},
        {'label': 'Query Plan', 'action': 'manage_catalogPlan'},
        {'label': 'Undo', 'action': 'manage_UndoForm'},
        {'label': 'Security', 'action': 'manage_access'},
        {'label': 'Ownership', 'action': 'manage_owner'},
        )

    security.declareProtected(manage_zcatalog_entries, 'manage_main')

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogView')
    manage_catalogView = DTMLFile('dtml/catalogView', globals())

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogIndexes')
    manage_catalogIndexes = DTMLFile('dtml/catalogIndexes', globals())

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogSchema')
    manage_catalogSchema = DTMLFile('dtml/catalogSchema', globals())

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogFind')
    manage_catalogFind = DTMLFile('dtml/catalogFind', globals())

    security.declareProtected(manage_zcatalog_entries,
                              'manage_catalogAdvanced')
    manage_catalogAdvanced = DTMLFile('dtml/catalogAdvanced', globals())

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogReport')
    manage_catalogReport = DTMLFile('dtml/catalogReport', globals())

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogPlan')
    manage_catalogPlan = DTMLFile('dtml/catalogPlan', globals())

    security.declareProtected(manage_zcatalog_entries,
                              'manage_objectInformation')
    manage_objectInformation = DTMLFile('dtml/catalogObjectInformation',
                                        globals())

    Indexes = ZCatalogIndexes()

    threshold = 10000
    long_query_time = 0.1

    # vocabulary and vocab_id are left for backwards
    # compatibility only, they are not used anymore
    vocabulary = None
    vocab_id = ''

    _v_total = 0
    _v_transaction = None

    def __init__(self, id, title='', vocab_id=None, container=None):
        # ZCatalog no longer cares about vocabularies
        # so the vocab_id argument is ignored (Casey)

        if container is not None:
            self = self.__of__(container)
        self.id=id
        self.title=title
        self.threshold = 10000
        self.long_query_time = 0.1 # in seconds
        self._v_total = 0
        self._catalog = Catalog()

    def __len__(self):
        return len(self._catalog)

    security.declareProtected(manage_zcatalog_entries, 'manage_edit')
    def manage_edit(self, RESPONSE, URL1, threshold=1000, REQUEST=None):
        """ edit the catalog """
        if not isinstance(threshold, int):
            threshold = int(threshold)
        self.threshold = threshold

        RESPONSE.redirect(
            URL1 + '/manage_main?manage_tabs_message=Catalog%20Changed')

    security.declareProtected(manage_zcatalog_entries, 'manage_subbingToggle')
    def manage_subbingToggle(self, REQUEST, RESPONSE, URL1):
        """ toggle subtransactions """
        if self.threshold:
            self.threshold = None
        else:
            self.threshold = 10000

        RESPONSE.redirect(
            URL1 +
            '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Changed')

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogObject')
    def manage_catalogObject(self, REQUEST, RESPONSE, URL1, urls=None):
        """ index Zope object(s) that 'urls' point to """
        if urls:
            if isinstance(urls, str):
                urls = (urls, )

            for url in urls:
                obj = self.resolve_path(url)
                if obj is None and hasattr(self, 'REQUEST'):
                    obj = self.resolve_url(url, REQUEST)
                if obj is not None:
                    self.catalog_object(obj, url)

        RESPONSE.redirect(
            URL1 +
            '/manage_catalogView?manage_tabs_message=Object%20Cataloged')

    security.declareProtected(manage_zcatalog_entries,
                              'manage_uncatalogObject')
    def manage_uncatalogObject(self, REQUEST, RESPONSE, URL1, urls=None):
        """ removes Zope object(s) 'urls' from catalog """

        if urls:
            if isinstance(urls, str):
                urls = (urls, )

            for url in urls:
                self.uncatalog_object(url)

        RESPONSE.redirect(
            URL1 +
            '/manage_catalogView?manage_tabs_message=Object%20Uncataloged')

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogReindex')
    def manage_catalogReindex(self, REQUEST, RESPONSE, URL1):
        """ clear the catalog, then re-index everything """

        elapse = time.time()
        c_elapse = time.clock()

        pgthreshold = self._getProgressThreshold()
        handler = (pgthreshold > 0) and ZLogHandler(pgthreshold) or None
        self.refreshCatalog(clear=1, pghandler=handler)

        elapse = time.time() - elapse
        c_elapse = time.clock() - c_elapse

        RESPONSE.redirect(
            URL1 +
            '/manage_catalogAdvanced?manage_tabs_message=' +
            urllib.quote('Catalog Updated \n'
                         'Total time: %s\n'
                         'Total CPU time: %s' % (`elapse`, `c_elapse`)))

    security.declareProtected(manage_zcatalog_entries, 'refreshCatalog')
    def refreshCatalog(self, clear=0, pghandler=None):
        """ re-index everything we can find """

        cat = self._catalog
        paths = cat.paths.values()
        if clear:
            paths = tuple(paths)
            cat.clear()

        num_objects = len(paths)
        if pghandler:
            pghandler.init('Refreshing catalog: %s' % self.absolute_url(1),
                           num_objects)

        for i in xrange(num_objects):
            if pghandler:
                pghandler.report(i)

            p = paths[i]
            obj = self.resolve_path(p)
            if obj is None:
                obj = self.resolve_url(p, self.REQUEST)
            if obj is not None:
                try:
                    self.catalog_object(obj, p, pghandler=pghandler)
                except ConflictError:
                    raise
                except Exception:
                    LOG.error('Recataloging object at %s failed' % p,
                              exc_info=sys.exc_info())

        if pghandler:
            pghandler.finish()

    security.declareProtected(manage_zcatalog_entries, 'manage_catalogClear')
    def manage_catalogClear(self, REQUEST=None, RESPONSE=None, URL1=None):
        """ clears the whole enchilada """
        self._catalog.clear()

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
              URL1 +
              '/manage_catalogAdvanced?manage_tabs_message=Catalog%20Cleared')

    security.declareProtected(manage_zcatalog_entries,
                              'manage_catalogFoundItems')
    def manage_catalogFoundItems(self, REQUEST, RESPONSE, URL2, URL1,
                                 obj_metatypes=None,
                                 obj_ids=None, obj_searchterm=None,
                                 obj_expr=None, obj_mtime=None,
                                 obj_mspec=None, obj_roles=None,
                                 obj_permission=None):
        """ Find object according to search criteria and Catalog them
        """
        elapse = time.time()
        c_elapse = time.clock()

        obj = REQUEST.PARENTS[1]
        path = '/'.join(obj.getPhysicalPath())

        self.ZopeFindAndApply(obj,
                              obj_metatypes=obj_metatypes,
                              obj_ids=obj_ids,
                              obj_searchterm=obj_searchterm,
                              obj_expr=obj_expr,
                              obj_mtime=obj_mtime,
                              obj_mspec=obj_mspec,
                              obj_permission=obj_permission,
                              obj_roles=obj_roles,
                              search_sub=1,
                              REQUEST=REQUEST,
                              apply_func=self.catalog_object,
                              apply_path=path)

        elapse = time.time() - elapse
        c_elapse = time.clock() - c_elapse

        RESPONSE.redirect(
            URL1 +
            '/manage_catalogView?manage_tabs_message=' +
            urllib.quote('Catalog Updated\n'
                         'Total time: %s\n'
                         'Total CPU time: %s'
                         % (`elapse`, `c_elapse`)))

    security.declareProtected(manage_zcatalog_entries, 'manage_addColumn')
    def manage_addColumn(self, name, REQUEST=None, RESPONSE=None, URL1=None):
        """ add a column """
        self.addColumn(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
                URL1 +
                '/manage_catalogSchema?manage_tabs_message=Column%20Added')

    security.declareProtected(manage_zcatalog_entries, 'manage_delColumn')
    def manage_delColumn(self, names, REQUEST=None, RESPONSE=None, URL1=None):
        """ delete a column or some columns """
        if isinstance(names, str):
            names = (names, )

        for name in names:
            self.delColumn(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
                URL1 +
                '/manage_catalogSchema?manage_tabs_message=Column%20Deleted')

    security.declareProtected(manage_zcatalog_entries, 'manage_addIndex')
    def manage_addIndex(self, name, type, extra=None,
                        REQUEST=None, RESPONSE=None, URL1=None):
        """add an index """
        self.addIndex(name, type, extra)

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
                URL1 +
                '/manage_catalogIndexes?manage_tabs_message=Index%20Added')

    security.declareProtected(manage_zcatalog_entries, 'manage_delIndex')
    def manage_delIndex(self, ids=None, REQUEST=None, RESPONSE=None,
        URL1=None):
        """ delete an index or some indexes """
        if not ids:
            return MessageDialog(title='No items specified',
                message='No items were specified!',
                action="./manage_catalogIndexes")

        if isinstance(ids, str):
            ids = (ids, )

        for name in ids:
            self.delIndex(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
                URL1 +
                '/manage_catalogIndexes?manage_tabs_message=Index%20Deleted')

    security.declareProtected(manage_zcatalog_entries, 'manage_clearIndex')
    def manage_clearIndex(self, ids=None, REQUEST=None, RESPONSE=None,
        URL1=None):
        """ clear an index or some indexes """
        if not ids:
            return MessageDialog(title='No items specified',
                message='No items were specified!',
                action="./manage_catalogIndexes")

        if isinstance(ids, str):
            ids = (ids, )

        for name in ids:
            self.clearIndex(name)

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
                URL1 +
                '/manage_catalogIndexes?manage_tabs_message=Index%20Cleared')

    security.declareProtected(manage_zcatalog_entries, 'reindexIndex')
    def reindexIndex(self, name, REQUEST, pghandler=None):
        if isinstance(name, str):
            name = (name, )

        paths = self._catalog.uids.keys()

        i = 0
        if pghandler:
            pghandler.init('reindexing %s' % name, len(paths))

        for p in paths:
            i += 1
            if pghandler:
                pghandler.report(i)

            obj = self.resolve_path(p)
            if obj is None:
                obj = self.resolve_url(p, REQUEST)
            if obj is None:
                LOG.error('reindexIndex could not resolve '
                          'an object from the uid %r.' % p)
            else:
                # don't update metadata when only reindexing a single
                # index via the UI
                self.catalog_object(obj, p, idxs=name,
                                    update_metadata=0, pghandler=pghandler)

        if pghandler:
            pghandler.finish()

    security.declareProtected(manage_zcatalog_entries, 'manage_reindexIndex')
    def manage_reindexIndex(self, ids=None, REQUEST=None, RESPONSE=None,
                            URL1=None):
        """Reindex indexe(s) from a ZCatalog"""
        if not ids:
            return MessageDialog(title='No items specified',
                message='No items were specified!',
                action="./manage_catalogIndexes")

        pgthreshold = self._getProgressThreshold()
        handler = (pgthreshold > 0) and ZLogHandler(pgthreshold) or None
        self.reindexIndex(ids, REQUEST, handler)

        if REQUEST and RESPONSE:
            RESPONSE.redirect(
                URL1 +
                '/manage_catalogIndexes'
                '?manage_tabs_message=Reindexing%20Performed')

    security.declareProtected(manage_zcatalog_entries, 'catalog_object')
    def catalog_object(self, obj, uid=None, idxs=None, update_metadata=1,
                       pghandler=None):
        if uid is None:
            try:
                uid = obj.getPhysicalPath
            except AttributeError:
                raise CatalogError(
                    "A cataloged object must support the 'getPhysicalPath' "
                    "method if no unique id is provided when cataloging")
            else:
                uid = '/'.join(uid())
        elif not isinstance(uid, str):
            raise CatalogError('The object unique id must be a string.')

        self._catalog.catalogObject(obj, uid, None, idxs,
                                    update_metadata=update_metadata)
        # None passed in to catalogObject as third argument indicates
        # that we shouldn't try to commit subtransactions within any
        # indexing code.  We throw away the result of the call to
        # catalogObject (which is a word count), because it's
        # worthless to us here.

        if self.threshold is not None:
            # figure out whether or not to commit a subtransaction.
            t = id(transaction.get())
            if t != self._v_transaction:
                self._v_total = 0
            self._v_transaction = t
            self._v_total = self._v_total + 1
            # increment the _v_total counter for this thread only and get
            # a reference to the current transaction.
            # the _v_total counter is zeroed if we notice that we're in
            # a different transaction than the last one that came by.
            # self.threshold represents the number of times that
            # catalog_object needs to be called in order for the catalog
            # to commit a subtransaction.  The semantics here mean that
            # we should commit a subtransaction if our threshhold is
            # exceeded within the boundaries of the current transaction.
            if self._v_total > self.threshold:
                transaction.savepoint(optimistic=True)
                self._p_jar.cacheGC()
                self._v_total = 0
                if pghandler:
                    pghandler.info('committing subtransaction')

    security.declareProtected(manage_zcatalog_entries, 'uncatalog_object')
    def uncatalog_object(self, uid):
        self._catalog.uncatalogObject(uid)

    security.declareProtected(search_zcatalog, 'uniqueValuesFor')
    def uniqueValuesFor(self, name):
        # Return the unique values for a given FieldIndex
        return self._catalog.uniqueValuesFor(name)

    security.declareProtected(search_zcatalog, 'getpath')
    def getpath(self, rid):
        # Return the path to a cataloged object given a 'data_record_id_'
        return self._catalog.paths[rid]

    security.declareProtected(search_zcatalog, 'getrid')
    def getrid(self, path, default=None):
        # Return 'data_record_id_' the to a cataloged object given a 'path'
        return self._catalog.uids.get(path, default)

    security.declareProtected(search_zcatalog, 'getobject')
    def getobject(self, rid, REQUEST=None):
        # Return a cataloged object given a 'data_record_id_'
        return aq_parent(self).unrestrictedTraverse(self.getpath(rid))

    security.declareProtected(search_zcatalog, 'getMetadataForUID')
    def getMetadataForUID(self, uid):
        # return the correct metadata given the uid, usually the path
        rid = self._catalog.uids[uid]
        return self._catalog.getMetadataForRID(rid)

    security.declareProtected(search_zcatalog, 'getIndexDataForUID')
    def getIndexDataForUID(self, uid):
        # return the current index contents given the uid, usually the path
        rid = self._catalog.uids[uid]
        return self._catalog.getIndexDataForRID(rid)

    security.declareProtected(search_zcatalog, 'getMetadataForRID')
    def getMetadataForRID(self, rid):
        # return the correct metadata for the cataloged record id
        return self._catalog.getMetadataForRID(int(rid))

    security.declareProtected(search_zcatalog, 'getIndexDataForRID')
    def getIndexDataForRID(self, rid):
        # return the current index contents for the specific rid
        return self._catalog.getIndexDataForRID(rid)

    security.declareProtected(search_zcatalog, 'schema')
    def schema(self):
        return self._catalog.schema.keys()

    security.declareProtected(search_zcatalog, 'indexes')
    def indexes(self):
        return self._catalog.indexes.keys()

    security.declareProtected(search_zcatalog, 'index_objects')
    def index_objects(self):
        # This method returns unwrapped indexes!
        # You should probably use getIndexObjects instead
        return self._catalog.indexes.values()

    security.declareProtected(manage_zcatalog_indexes, 'getIndexObjects')
    def getIndexObjects(self):
        # Return a list of wrapped(!) indexes
        getIndex = self._catalog.getIndex
        return [getIndex(name) for name in self.indexes()]

    def _searchable_arguments(self):
        r = {}
        n = {'optional': 1}
        for name in self._catalog.indexes.keys():
            r[name] = n
        return r

    def _searchable_result_columns(self):
        r = []
        for name in self._catalog.schema.keys():
            i = {}
            i['name'] = name
            i['type'] = 's'
            i['parser'] = str
            i['width'] = 8
            r.append(i)
        r.append({'name': 'data_record_id_',
                  'type': 's',
                  'parser': str,
                  'width': 8})
        return r

    security.declareProtected(search_zcatalog, 'searchResults')
    def searchResults(self, REQUEST=None, used=None, **kw):
        """Search the catalog

        Search terms can be passed in the REQUEST or as keyword
        arguments.

        The used argument is now deprecated and ignored
        """

        return self._catalog.searchResults(REQUEST, used, **kw)

    security.declareProtected(search_zcatalog, '__call__')
    __call__ = searchResults

    security.declareProtected(search_zcatalog, 'search')
    def search(
        self, query_request, sort_index=None, reverse=0, limit=None, merge=1):
        """Programmatic search interface, use for searching the catalog from
        scripts.

        query_request: Dictionary containing catalog query
        sort_index:    Name of sort index
        reverse:       Reverse sort order?
        limit:         Limit sorted result count (optimization hint)
        merge:         Return merged results (like searchResults) or raw
                       results for later merging.
        """
        if sort_index is not None:
            sort_index = self._catalog.indexes[sort_index]
        return self._catalog.search(
            query_request, sort_index, reverse, limit, merge)

    ## this stuff is so the find machinery works

    meta_types=() # Sub-object types that are specific to this object

    security.declareProtected(search_zcatalog, 'valid_roles')
    def valid_roles(self):
        # Return list of valid roles
        obj=self
        dict={}
        dup =dict.has_key
        x=0
        while x < 100:
            if hasattr(obj, '__ac_roles__'):
                roles=obj.__ac_roles__
                for role in roles:
                    if not dup(role):
                        dict[role]=1
            obj = aq_parent(obj)
            if obj is None:
                break
            x = x + 1
        roles=dict.keys()
        roles.sort()
        return roles

    security.declareProtected(manage_zcatalog_entries, 'ZopeFindAndApply')
    def ZopeFindAndApply(self, obj, obj_ids=None, obj_metatypes=None,
                         obj_searchterm=None, obj_expr=None,
                         obj_mtime=None, obj_mspec=None,
                         obj_permission=None, obj_roles=None,
                         search_sub=0,
                         REQUEST=None, result=None, pre='',
                         apply_func=None, apply_path=''):
        """Zope Find interface and apply

        This is a *great* hack.  Zope find just doesn't do what we
        need here; the ability to apply a method to all the objects
        *as they're found* and the need to pass the object's path into
        that method.
        """

        if result is None:
            result = []

            if obj_metatypes and 'all' in obj_metatypes:
                obj_metatypes = None

            if obj_mtime and isinstance(obj_mtime, str):
                obj_mtime = DateTime(obj_mtime).timeTime()

            if obj_permission:
                obj_permission = p_name(obj_permission)

            if obj_roles and isinstance(obj_roles, str):
                obj_roles = [obj_roles]

            if obj_expr:
                # Setup expr machinations
                md = td()
                obj_expr = (Eval(obj_expr), md, md._push, md._pop)

        base = aq_base(obj)

        if not hasattr(base, 'objectItems'):
            return result
        try:
            items = obj.objectItems()
        except Exception:
            return result

        try:
            add_result = result.append
        except Exception:
            raise AttributeError(repr(result))

        for id, ob in items:
            if pre:
                p = "%s/%s" % (pre, id)
            else:
                p = id

            dflag = 0
            if hasattr(ob, '_p_changed') and (ob._p_changed == None):
                dflag = 1

            bs = aq_base(ob)

            if (
                (not obj_ids or absattr(bs.id) in obj_ids)
                and
                (not obj_metatypes or (hasattr(bs, 'meta_type') and
                 bs.meta_type in obj_metatypes))
                and
                (not obj_searchterm or
                 (hasattr(ob, 'PrincipiaSearchSource') and
                  ob.PrincipiaSearchSource().find(obj_searchterm) >= 0))
                and
                (not obj_expr or expr_match(ob, obj_expr))
                and
                (not obj_mtime or mtime_match(ob, obj_mtime, obj_mspec))
                and
                ((not obj_permission or not obj_roles) or
                  role_match(ob, obj_permission, obj_roles))
                ):
                if apply_func:
                    apply_func(ob, (apply_path + '/' + p))
                else:
                    add_result((p, ob))
                    dflag = 0

            if search_sub and hasattr(bs, 'objectItems'):
                self.ZopeFindAndApply(ob, obj_ids, obj_metatypes,
                                      obj_searchterm, obj_expr,
                                      obj_mtime, obj_mspec,
                                      obj_permission, obj_roles,
                                      search_sub,
                                      REQUEST, result, p,
                                      apply_func, apply_path)
            if dflag:
                ob._p_deactivate()

        return result

    security.declareProtected(search_zcatalog, 'resolve_url')
    def resolve_url(self, path, REQUEST):
        # Attempt to resolve a url into an object in the Zope
        # namespace. The url may be absolute or a catalog path
        # style url. If no object is found, None is returned.
        # No exceptions are raised.
        if REQUEST:
            script=REQUEST.script
            if path.find(script) != 0:
                path='%s/%s' % (script, path)
            try:
                return REQUEST.resolve_url(path)
            except Exception:
                pass

    security.declareProtected(search_zcatalog, 'resolve_path')
    def resolve_path(self, path):
        # Attempt to resolve a url into an object in the Zope
        # namespace. The url may be absolute or a catalog path
        # style url. If no object is found, None is returned.
        # No exceptions are raised.
        try:
            return self.unrestrictedTraverse(path)
        except Exception:
            pass

    security.declareProtected(manage_zcatalog_entries, 'manage_normalize_paths')
    def manage_normalize_paths(self, REQUEST):
        """Ensure that all catalog paths are full physical paths

        This should only be used with ZCatalogs in which all paths can
        be resolved with unrestrictedTraverse."""

        paths = self._catalog.paths
        uids = self._catalog.uids
        unchanged = 0
        fixed = []
        removed = []

        for path, rid in uids.items():
            ob = None
            if path[:1] == '/':
                ob = self.resolve_url(path[1:], REQUEST)
            if ob is None:
                ob = self.resolve_url(path, REQUEST)
                if ob is None:
                    removed.append(path)
                    continue
            ppath = '/'.join(ob.getPhysicalPath())
            if path != ppath:
                fixed.append((path, ppath))
            else:
                unchanged = unchanged + 1

        for path, ppath in fixed:
            rid = uids[path]
            del uids[path]
            paths[rid] = ppath
            uids[ppath] = rid
        for path in removed:
            self.uncatalog_object(path)

        return MessageDialog(title='Done Normalizing Paths',
          message='%s paths normalized, %s paths removed, and '
                  '%s unchanged.' % (len(fixed), len(removed), unchanged),
          action='./manage_main')

    security.declareProtected(manage_zcatalog_entries, 'manage_setProgress')
    def manage_setProgress(self, pgthreshold=0, RESPONSE=None, URL1=None):
        """Set parameter to perform logging of reindexing operations very
           'pgthreshold' objects
        """
        self.pgthreshold = pgthreshold
        if RESPONSE:
            RESPONSE.redirect(URL1 + '/manage_catalogAdvanced?'
                              'manage_tabs_message=Catalog%20Changed')

    def _getProgressThreshold(self):
        if not hasattr(self, 'pgthreshold'):
            self.pgthreshold = 0
        return self.pgthreshold

    # Indexing methods

    security.declareProtected(manage_zcatalog_indexes, 'addIndex')
    def addIndex(self, name, type, extra=None):
        if IPluggableIndex.providedBy(type):
            self._catalog.addIndex(name, type)
            return

        # Convert the type by finding an appropriate product which supports
        # this interface by that name.  Bleah
        products = ObjectManager.all_meta_types(self,
                                                interfaces=(IPluggableIndex, ))

        p = None

        for prod in products:
            if prod['name'] == type:
                p = prod
                break

        if p is None:
            raise ValueError("Index of type %s not found" % type)

        base = p['instance']

        if base is None:
            raise ValueError("Index type %s does not support addIndex" % type)

        # This code is *really* lame but every index type has its own
        # function signature *sigh* and there is no common way to pass
        # additional parameters to the constructor. The suggested way
        # for new index types is to use an "extra" record.

        if 'extra' in base.__init__.func_code.co_varnames:
            index = base(name, extra=extra, caller=self)
        elif 'caller' in base.__init__.func_code.co_varnames:
            index = base(name, caller=self)
        else:
            index = base(name)

        self._catalog.addIndex(name, index)

    security.declareProtected(manage_zcatalog_indexes, 'delIndex')
    def delIndex(self, name):
        self._catalog.delIndex(name)

    security.declareProtected(manage_zcatalog_indexes, 'clearIndex')
    def clearIndex(self, name):
        self._catalog.getIndex(name).clear()

    security.declareProtected(manage_zcatalog_indexes, 'addColumn')
    def addColumn(self, name, default_value=None):
        return self._catalog.addColumn(name, default_value)

    security.declareProtected(manage_zcatalog_indexes, 'delColumn')
    def delColumn(self, name):
        return self._catalog.delColumn(name)

    # Catalog plan methods

    security.declareProtected(manage_zcatalog_entries, 'getCatalogPlan')
    def getCatalogPlan(self):
        """Get a string representation of a query plan"""
        pmap = PriorityMap.get_value()
        output = []
        output.append('# query plan dumped at %r\n' % time.asctime())
        output.append('queryplan = {')
        for cid, plan in sorted(pmap.items()):
            output.append('  %s: {' % repr(cid))
            for querykey, details in sorted(plan.items()):
                output.append('    %s: {' % repr(querykey))
                for indexname, benchmark in sorted(details.items()):
                    tuplebench = (round(benchmark[0], 4), ) + benchmark[1:]
                    output.append('      %r:\n      %r,' % (indexname, tuplebench))
                output.append('    },')
            output.append('  },')
        output.append('}')
        return '\n'.join(output)

    security.declareProtected(manage_zcatalog_entries, 'getCatalogReport')
    def getCatalogReport(self):
        """Query time reporting."""
        rval = self._catalog.getCatalogPlan().report()
        rval.sort(key=operator.itemgetter('duration'), reverse=True)
        return rval

    security.declareProtected(manage_zcatalog_entries,
                              'manage_resetCatalogReport')
    def manage_resetCatalogReport(self, REQUEST=None):
        """Resets the catalog report."""
        self._catalog.getCatalogPlan().reset()

        if REQUEST is not None:
            REQUEST.response.redirect(REQUEST.URL1 +
                '/manage_catalogReport?manage_tabs_message=Report%20cleared')

    security.declareProtected(manage_zcatalog_entries,
                              'manage_editCatalogReport')
    def manage_editCatalogReport(self, long_query_time=0.1, REQUEST=None):
        """Edit the long query time."""
        if not isinstance(long_query_time, float):
            long_query_time = float(long_query_time)
        self.long_query_time = long_query_time

        if REQUEST is not None:
            REQUEST.response.redirect(REQUEST.URL1 +
                '/manage_catalogReport?manage_tabs_message=' +
                'Long%20query%20time%20changed')

    def manage_convertIndexes(self, REQUEST=None, RESPONSE=None, URL1=None):
        pass

InitializeClass(ZCatalog)


def p_name(name):
    return '_' + string.translate(name, name_trans) + '_Permission'


def absattr(attr):
    if callable(attr):
        return attr()
    return attr


class td(RestrictedDTML, TemplateDict):
    pass


def expr_match(ob, ed):
    e, md, push, pop = ed
    push(InstanceDict(ob, md))
    r = 0
    try:
        r = e.eval(md)
    finally:
        pop()
        return r

_marker = object()


def mtime_match(ob, t, q):
    mtime = getattr(ob, '_p_mtime', _marker)
    if mtime is _marker():
        return False
    return q=='<' and (mtime < t) or (mtime > t)


def role_match(ob, permission, roles):
    pr = []
    while True:
        p = getattr(ob, permission, _marker)
        if p is not _marker:
            if isinstance(p, list):
                pr.append(p)
                ob = aq_parent(ob)
                if ob is not None:
                    continue
                break
            if isinstance(p, tuple):
                pr.append(p)
                break
            if p is None:
                pr.append(('Manager', 'Anonymous'))
                break

        ob = aq_parent(ob)
        if ob is not None:
            continue
        break

    for role in roles:
        if role not in pr:
            return False
    return True
