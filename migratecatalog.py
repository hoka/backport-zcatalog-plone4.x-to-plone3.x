import cPickle as pickle

def main(self):
    """ """
    migrator=Migrator(self)
    #migrator.exportPath()
    #migrator.addFieldsAndSchema()
    migrator.rebuildCatalog()

class Migrator:

    path='/tmp/path'

    def __init__(self,context):
        """ """
        self.context=context


    def exportPath(self):
        """ """
        context=self.context
        pc=context.portal_catalog
        paths=list(pc._catalog.indexes['path']._unindex.values())
        data=pickle.dumps(paths)
        open(self.path,'wb').write(data)

    def rebuildCatalog(self):
        """ """
        context=self.context
        pc=context.portal_catalog
        portal=context.portal_url.getPortalObject()
        data=open(self.path,'rb').read()
        counter=0
        for path in pickle.loads(data):
            object_=portal.unrestrictedTraverse(path)
            pc.catalog_object(object_,path)
            counter+=1
            print counter




    def addFieldsAndSchema(self):
        """ """
        context=self.context
        pc=context.portal_catalog
        portal=context.portal_url.getPortalObject()

        class args:
            def __init__(self, **kw):
                self.__dict__.update(kw)
            def keys(self):
                return self.__dict__.keys()

        pc.manage_addProduct['ZCTextIndex'].manage_addLexicon(
            'htmltext_lexicon',
            elements=[
                args(group='Word Splitter', name='HTML aware splitter'),
                args(group='Case Normalizer', name="Case Normalizer"),
                args(group='Stop Words', name="Remove listed stop words only"),
                ]
                )

        pc.manage_addProduct['ZCTextIndex'].manage_addLexicon(
            'plaintext_lexicon',
            elements=[
                args(group='Word Splitter', name='Whitespace splitter'),
                args(group='Case Normalizer', name="Case Normalizer"),
                args(group='Stop Words', name="Remove listed stop words only"),
                ]
                )

        pc.manage_addProduct['ZCTextIndex'].manage_addLexicon(
            'plone_lexicon',
            elements=[
                args(group='Word Splitter', name='Unicode Whitespace splitter'),
                args(group='Case Normalizer', name="Case Normalizer"),
                ]
                )

        if not pc._catalog.schema.has_key('Creator'):
            pc.addColumn('Creator')
        if not pc._catalog.schema.has_key('Description'):
            pc.addColumn('Description')
        if not pc._catalog.schema.has_key('Language'):
            pc.addColumn('Language')
        if not pc._catalog.schema.has_key('Subject'):
            pc.addColumn('Subject')
        if not pc._catalog.schema.has_key('Title'):
            pc.addColumn('Title')
        if not pc._catalog.schema.has_key('UID'):
            pc.addColumn('UID')
        if not pc._catalog.schema.has_key('cmf_uid'):
            pc.addColumn('cmf_uid')
        if not pc._catalog.schema.has_key('created'):
            pc.addColumn('created')
        if not pc._catalog.schema.has_key('effective'):
            pc.addColumn('effective')
        if not pc._catalog.schema.has_key('end'):
            pc.addColumn('end')
        if not pc._catalog.schema.has_key('exclude_from_nav'):
            pc.addColumn('exclude_from_nav')
        if not pc._catalog.schema.has_key('expires'):
            pc.addColumn('expires')
        if not pc._catalog.schema.has_key('getIcon'):
            pc.addColumn('getIcon')
        if not pc._catalog.schema.has_key('getId'):
            pc.addColumn('getId')
        if not pc._catalog.schema.has_key('getLayout'):
            pc.addColumn('getLayout')
        if not pc._catalog.schema.has_key('getObjSize'):
            pc.addColumn('getObjSize')
        if not pc._catalog.schema.has_key('listCreators'):
            pc.addColumn('listCreators')
        if not pc._catalog.schema.has_key('location'):
            pc.addColumn('location')
        if not pc._catalog.schema.has_key('meta_type'):
            pc.addColumn('meta_type')
        if not pc._catalog.schema.has_key('modified'):
            pc.addColumn('modified')
        if not pc._catalog.schema.has_key('portal_type'):
            pc.addColumn('portal_type')
        if not pc._catalog.schema.has_key('review_state'):
            pc.addColumn('review_state')
        if not pc._catalog.schema.has_key('start'):
            pc.addColumn('start')


        if 'Creator' not in pc.indexes():
            pc.addIndex('Creator', 'FieldIndex')
        if 'Language' not in pc.indexes():
            pc.addIndex('Language', 'FieldIndex')

        if 'SearchableText' not in pc.indexes():
            class _extra:
                pass

            extra = _extra()
            extra.lexicon_id = 'plone_lexicon'
            extra.index_type = 'Okapi BM25 Rank'
            pc.addIndex('foo_zctext', 'ZCTextIndex', extra)

        """
        if 'SearchableText' not in pc.indexes():
            class _extra:
                lexicon_id="plone_lexicon"
                index_type="Okapi BM25 Rank"
            extra=_extra()

            pc.addIndex('SearchableText', 'TextIndexNG3',extra=extra)
            searchableTextIndex=pc._catalog.getIndex('SearchableText')
            searchableTextIndex.index.edit(fields=['SearchableText'],
                           lexicon='txng.lexicons.default',
                           storage='txng.storages.default',
                           splitter='txng.splitters.default',
                           autoexpand='on_miss',
                           autoexpand_limit=4,
                           query_parser='txng.parsers.en',
                           use_stemmer=False,
                           languages=('en',),
                           use_stopwords=True,
                           default_encoding='utf-8',
                           use_normalizer=True,
                           dedicated_storage=True,
                           splitter_casefolding=True,
                           splitter_additional_chars='',
                           index_unknown_languages=True,
                           ranking=False,
                           ranking_method='txng.ranking.cosine',
                           )
            searchableTextIndex.index.clear()
        """
        if 'Subject' not in pc.indexes():
            pc.addIndex('Subject', 'KeywordIndex')
        if 'UID' not in pc.indexes():
            pc.addIndex('UID', 'FieldIndex')
        if 'allowedRolesAndUsers' not in pc.indexes():
            pc.addIndex('allowedRolesAndUsers', 'KeywordIndex')
        if 'cmf_uid' not in pc.indexes():
            pc.addIndex('cmf_uid', 'FieldIndex')
        if 'created' not in pc.indexes():
            pc.addIndex('created', 'DateIndex')
        if 'effective' not in pc.indexes():
            pc.addIndex('effective', 'DateIndex')
        if 'end' not in pc.indexes():
            pc.addIndex('end', 'DateIndex')
        if 'expires' not in pc.indexes():
            pc.addIndex('expires', 'DateIndex')
        if 'getCode' not in pc.indexes():
            pc.addIndex('getCode', 'KeywordIndex')
        if 'getCodeIndex' not in pc.indexes():
            pc.addIndex('getCodeIndex', 'FieldIndex')
        if 'getCustomSearch' not in pc.indexes():
            pc.addIndex('getCustomSearch', 'KeywordIndex')
        if 'getEffectiveIndex' not in pc.indexes():
            pc.addIndex('getEffectiveIndex', 'FieldIndex')
        if 'getExcludeFromNav' not in pc.indexes():
            pc.addIndex('getExcludeFromNav', 'FieldIndex')
        if 'getExcludeFromSearch' not in pc.indexes():
            pc.addIndex('getExcludeFromSearch', 'FieldIndex')
        if 'getObjPositionInParent' not in pc.indexes():
            pc.addIndex('getObjPositionInParent', 'FieldIndex')
        if 'getTitleIndex' not in pc.indexes():
            pc.addIndex('getTitleIndex', 'FieldIndex')
        if 'getUsedLanguages' not in pc.indexes():
            pc.addIndex('getUsedLanguages', 'KeywordIndex')
        if 'is_default_page' not in pc.indexes():
            pc.addIndex('is_default_page', 'FieldIndex')
        if 'is_folderish' not in pc.indexes():
            pc.addIndex('is_folderish', 'FieldIndex')
        if 'modified' not in pc.indexes():
            pc.addIndex('modified', 'DateIndex')
        if 'path' not in pc.indexes():
            pc.addIndex('path', 'ExtendedPathIndex')
        if 'portal_type' not in pc.indexes():
            pc.addIndex('portal_type', 'FieldIndex')
        if 'review_state' not in pc.indexes():
            pc.addIndex('review_state', 'FieldIndex')
        if 'sortable_title' not in pc.indexes():
            pc.addIndex('sortable_title', 'FieldIndex')
        if 'start' not in pc.indexes():
            pc.addIndex('start', 'DateIndex')

