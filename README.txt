Manual for Migration.

Backup your instance!
The whole process will take a while so make a maintenance window with your customer.
Try the steps below first in a copy of you site to be sure it works for you too.

-Move migratecatalog to Extension directory
-Edit the added indexes and metadata entries so it mirror your catalog schema and indexes
-Install the migration script as "External Method".
-Open the script an run migrator.exportPath()
-Go to Control Panel -> Product Management and remove the three Products ZCatlaog, PluginIndexes, ZCTextIndex
-Delete portal_catlaog in zmi
-Move the three Products to product directory
-Copy stopper.so and okascore.so from the existing version of ZCTextIndex to the moved ZCTextIndex.
-Copy the splitter *.so files from 'Textindex/Splitter/ISO_8859_1_Splitter, UnicodeSplitter, ZopeSplitter from the
 existing version of ZCTextIndex to the moved ZCTextIndex splitter directories.
-restart instance
-Go in zmi to plone site root and add under "Select type to add" -> Add Plone Tool -> Plone Catalog Tool
-Run migrator.addFieldsAndSchema() from the migration script
-Run migrator.rebuildCatalog() from the migration script
-wait while reindexing

