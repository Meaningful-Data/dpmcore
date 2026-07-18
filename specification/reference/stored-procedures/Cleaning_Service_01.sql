
BEGIN 
-- General cleaning of unused objects

DECLARE @CurrentRelease int; --- = 1020000001
  
--- DJT Added to make CurrentRelease dynamic
  
SELECT @CurrentRelease = ReleaseID
FROM   [dbo].[Release]
WHERE  IsCurrent = 1;


-- 1. Delete all ModuleVersions that do not take any part in ModuleVersionCompositions (hence they are orphan)
-- First set EndRelease=Null to the Previous Version (if such a previous verison exists)
update mv 
set mv.EndReleaseID=Null 
from ModuleVersion mv 
inner join Module md on mv.ModuleID=md.ModuleID 
where mv.EndReleaseID=@CurrentRelease and md.isDocumentModule=0 and 
mv.ModuleID in 
     (select mv2.Moduleid 
	  from ModuleVersion mv2 
	  where mv2.StartReleaseID=@CurrentRelease and 
	        mv2.EndReleaseID is Null and 
			mv2.ModuleVID not in (select Modulevid from ModuleVersionComposition)
			) 


delete mv  from ModuleVersion mv 
inner join module md on mv.ModuleID=md.ModuleID 
where (mv.ModuleVID not in (select ModuleVID from ModuleVersionComposition)) 
and mv.StartReleaseID=@CurrentRelease and md.isDocumentModule=0



-- DECLARE @CurrentRelease int = 2
-- 2. Delete all TableVersions that do not take any part in ModuleVersionCompositions (hence they are orphan)
-- First set EndRelease=Null to the Previous Version (if such a previous verison exists)
update tv 
set tv.EndReleaseID=Null 
from TableVersion  tv 
where (tv.EndReleaseID=@CurrentRelease OR tv.EndReleaseID=9999) and
tv.TableID in 
     (select tv2.Tableid 
	  from TableVersion tv2 
	  where (tv2.StartReleaseID=@CurrentRelease or tv2.StartReleaseID=9999) and 
	        tv2.EndReleaseID is Null and 
			tv2.TableVID not in (select Tablevid from ModuleVersionComposition)
			) 


-- First delete corrsponding TableVersionCells before deleting the TableVersion itself
delete tvc from TableVersionCell tvc inner join TableVersion tv on tv.TableVID=tvc.TableVID 
where (tv.TableVID not in (select TableVID from ModuleVersionComposition)) 
and (tv.StartReleaseID=@CurrentRelease or tv.StartReleaseID=9999)


-- Then delete corrsponding TableAssociations before deleting the TableVersion itself
--We delet choldtablevid and parenttabevid is cascaded
delete ta 
--select *
from TableAssociation ta inner join TableVersion tv on tv.TableVID=ta.ChildTableVID 
where (tv.TableVID not in (select TableVID from ModuleVersionComposition)) 
and (tv.StartReleaseID=@CurrentRelease or tv.StartReleaseID=9999)



-- Now delete TableVersions themselves
delete tv 
from TableVersion tv where (tv.TableVID not in (select TableVID from ModuleVersionComposition)) 
and (tv.StartReleaseID=@CurrentRelease or tv.StartReleaseID=9999)



-- 3. Delete all HeaderVersions not employed by any TableVersionHeader
-- First set EndRelease=Null to the Previous Version (if such a previous verison exists)
update hv 
set hv.EndReleaseID=Null 
from HeaderVersion  hv 
where (hv.EndReleaseID=@CurrentRelease or hv.EndReleaseID=9999) and
hv.HeaderID in 
     (select hv2.Headerid 
	  from HeaderVersion hv2 
	  where (hv2.StartReleaseID=@CurrentRelease or hv2.StartReleaseID=9999) and 
	        hv2.EndReleaseID is Null and 
	        hv2.HeaderVID not in (select Headervid from TableVersionHeader)
     ) 

delete hv from HeaderVersion hv where (not exists (select tvh.headervid from TableVersionHeader tvh where tvh.headervid=hv.headervid)) 
and (hv.StartReleaseID=@CurrentRelease or hv.StartReleaseID=9999)


-- 5. Delete any Cell that does not have any correspondent TableVersionCell
-- SOS!! This incoming deletion is very tricky! It may delete all Cells from Abstract Headers! 
-- But later if we convert from Abstract to Non-Abstract a Header then we would need to regenerate the corresponding cells in this case!
-- Still re-generation is supported by DRR; hence we can clean here
delete c from cell c where not exists (select tvc.cellid from tableversioncell tvc where tvc.cellid=c.CellID) 


-- 4. Delete all Headers for which no corresponding HeaderVersion exists and also there exist no cells corresponding to this header
delete h
from header h where (not exists (select hv.headerid from headerversion hv where hv.HeaderID=h.HeaderID) ) 
and (not exists (select c1.columnid from cell c1 where c1.ColumnID=h.HeaderID))
and (not exists (select c2.rowid from cell c2  where c2.RowID=h.HeaderID))
and (not exists (select c3.sheetid from cell c3  where c3.SheetID=h.HeaderID))


-- 6. Delete any Table that has not any corresponding TableVersion
delete t from [Table] t where (not exists (select tv.TableID from TableVersion tv where tv.TableID=t.TableID)) 


-- 7a. Delete All FACT VariableVersions not employed by any TableVersionCell
-- First set EndRelease=Null to the Previous Version (if such a previous verison exists)
update vv 
set vv.EndReleaseID=Null 
from VariableVersion  vv 
where vv.EndReleaseID=@CurrentRelease and
vv.VariableID in 
     (select vv2.Variableid 
	  from VariableVersion vv2 INNER JOIN Variable v2 on vv2.VariableID=v2.VariableID 
	  where vv2.StartReleaseID=@CurrentRelease and 
	        vv2.EndReleaseID is Null and 
			v2.Type='fact' and 
	        vv2.VariableVID not in (select Variablevid from TableVersionCell)
     ) 


delete vv 
from VariableVersion vv inner join variable v on vv.VariableID=v.VariableID where v.Type='fact'
and not exists (select tvc.Variablevid from TableVersionCell tvc where tvc.VariableVID=vv.VariableVID)  and vv.StartReleaseID=@CurrentRelease 


-- 7b. Delete All KEY VariableVersions not employed by any HeaderVersion or KeyComposition
-- First set EndRelease=Null to the Previous Version (if such a previous verison exists)
update vv 
set vv.EndReleaseID=Null 
from VariableVersion  vv 
where vv.EndReleaseID=@CurrentRelease and
vv.VariableID in 
     (select vv2.Variableid 
	  from VariableVersion vv2 INNER JOIN Variable v2 on vv2.VariableID=v2.VariableID 
	  where vv2.StartReleaseID=@CurrentRelease and 
	        vv2.EndReleaseID is Null and 
			v2.Type='key' and 
	        (not exists (select hv.KeyVariablevid from HeaderVersion hv where hv.KeyVariableVID=vv2.VariableVID)) and 
			(not exists (select kc.Variablevid from KeyComposition kc where kc.VariableVID=vv2.VariableVID))      ) 

delete vv from VariableVersion vv inner join variable v on vv.VariableID=v.VariableID 
where v.Type='key' and 
vv.StartReleaseID=@CurrentRelease AND 
(not exists (select hv.keyVariablevid from HeaderVersion hv where hv.KeyVariableVID=vv.VariableVID) ) and 
(not exists (select kc.VariableVID from KeyComposition kc where kc.VariableVID=vv.VariableVID) )


--declare @CurrentRelease int = 2
-- 7c. Delete All FILING INDICATOR VariableVersions not employed by any ModuleParameters
-- First set EndRelease=Null to the Previous Version (if such a previous verison exists)
update vv 
set vv.EndReleaseID=Null 
from VariableVersion  vv 
where vv.EndReleaseID=@CurrentRelease and
vv.VariableID in 
     (select vv2.Variableid 
	  from VariableVersion vv2 INNER JOIN Variable v2 on vv2.VariableID=v2.VariableID 
	  where vv2.StartReleaseID=@CurrentRelease and 
	        vv2.EndReleaseID is Null and 
			v2.Type='filingindicator' and 
	        vv2.VariableVID not in (select mp.Variablevid from ModuleParameters mp)      ) 
			

delete vv 
from VariableVersion vv inner join variable v on vv.VariableID=v.VariableID   and vv.StartReleaseID=@CurrentRelease 
where v.Type='filingindicator' and 
Not exists (select mp.Variablevid from ModuleParameters mp where mp.VariableVID=vv.VariableVID) 


-- 8. Delete any Variable that has not any corresponding VariableVersion
delete v from Variable v where not exists (select vv.* from VariableVersion vv where vv.VariableID=v.VariableID) 
and not exists (select vc.* from VariableCalculation vc where vc.VariableID=v.VariableID) 
and not exists (select orf.* from OperandReference orf where orf.VariableID=v.VariableID)


-- 9. Delete any Module that has not any corresponding ModuleVersion
delete from Module where moduleid not in (select mv.moduleid from moduleversion mv)


-- 9b. Delete any Framework that has not any existing corresponding Module.
delete
from Framework where frameworkid not in (select m.frameworkid from module m)


-- 10. Delete all Contexts not employed by any of: VariableVersion, HeaderVersion, TableVerison< CompountItemContext
-- Moreover, delete any Context (and also delete it previously from the above related DPM Objects) 
-- if for this ContextID there does not exist any entry in ContextComposiiton (i.e. it is any empty Context).
update tv
set tv.ContextID=null
from TableVersion tv 
where tv.ContextID is not Null and (not exists (select cc.ContextID from ContextComposition cc where cc.COntextID=tv.ContextID))


update hv
set hv.ContextID=null
from HeaderVersion hv 
where hv.ContextID is not Null and (not exists (select cc.ContextID from ContextComposition cc where cc.COntextID=hv.ContextID))

update vv
set vv.ContextID=null
from VariableVersion vv 
where vv.ContextID is not Null and (not exists (select cc.ContextID from ContextComposition cc where cc.COntextID=vv.ContextID))

update cic
set cic.ContextID=null
from CompoundItemContext cic 
where cic.ContextID is not Null and (not exists (select cc.ContextID from ContextComposition cc where cc.COntextID=cic.ContextID))

delete ct 
from Context ct where (not exists (select cc.ContextID from ContextComposition cc where cc.ContextID=ct.ContextID))


delete ct 
from context ct 
where 
(not exists (select vv.contextid from variableversion vv where vv.contextid=ct.contextid)) and 
(not exists (select hv.contextid from headerversion hv where hv.contextid=ct.contextid)) and 
(not exists (select tv.contextid from tableversion tv where tv.contextid=ct.contextid)) and 
(not exists (select cc.contextid from CompoundItemContext cc where cc.contextid=ct.contextid))


-- 11. Delete any CompoundKey whose KeyID is not employed first by any TableVersion, VariableVersion and ModuleVersion.
-- Moreover, delete any CompoundKey (and also delete it previously from the above related DPM Objects) 
-- if for this KeyID there does not exist any entry in KeyComposition (i.e. it is any empty Key).
-- DECLARE @CurrentRelease int = 2
update tv
set tv.KeyID=null
from TableVersion tv 
where tv.KeyID is not Null and (not exists (select kc.KeyID from KeyComposition kc where kc.KeyID=tv.KeyID)) and tv.StartReleaseID=@CurrentRelease


update vv
set vv.KeyID=null
from VariableVersion vv 
where vv.KeyID is not Null and (not exists (select kc.KeyID from KeyComposition kc where kc.KeyID=vv.KeyID)) and vv.StartReleaseID=@CurrentRelease


update mv
set mv.GlobalKeyID=null
from ModuleVersion mv 
where mv.GlobalKeyID is not Null and (not exists (select kc.KeyID from KeyComposition kc where kc.KeyID=mv.GlobalKeyID)) and mv.StartReleaseID=@CurrentRelease


delete ck 
from CompoundKey ck where (not exists (select kc.KeyID from KeyComposition kc where kc.KeyID=ck.KeyID))


delete ck 
from compoundkey ck 
where (not exists (select tv.keyid from TableVersion tv where ck.keyID=tv.KeyID) )
  and (not exists (select vv.keyid from VariableVersion vv where ck.keyID=vv.KeyID) )
  and (not exists (select mv.Globalkeyid from ModuleVersion mv where ck.keyID=mv.GlobalKeyID) )
  


-- 12. Delete all SubCategoryVersions not eployed by any of: VariableVersion, HeaderVersion
-- Before deleting such SubCategoryVersions (which have StartRelease=@CurrentRelease otherwise they would have been cleaned before) 
-- check if tghere exist previous Version to them
-- If there exists set: prev_Version.EndReleaseID=Null
--update scv 
--set scv.EndReleaseID=Null 
--from subcategoryversion  scv 
--where scv.EndReleaseID=@CurrentRelease and
--scv.SubCategoryID in 
--     (select scv2.subcategoryid 
--	  from subcategoryversion scv2 
--	  where scv2.StartReleaseID=@CurrentRelease and 
--	        scv2.EndReleaseID is Null and 
--	        (not exists (select vv.subcategoryvid from variableversion vv where vv.SubCategoryVID=scv2.SubCategoryVID)) and
--			(not exists (select hv.subcategoryvid from headerversion hv  where hv.SubCategoryVID=scv2.SubCategoryVID))
--     ) 

  -- DECLARE @CurrentRelease int = 2
--delete scv2 
--from subcategoryversion scv2 
--where scv2.StartReleaseID=@CurrentRelease and 
--	        scv2.EndReleaseID is Null and 
--	        (not exists (select vv.subcategoryvid from variableversion vv where vv.SubCategoryVID=scv2.SubCategoryVID)) and
--			(not exists (select hv.subcategoryvid from headerversion hv  where hv.SubCategoryVID=scv2.SubCategoryVID))
     


-- Even More General Cleaning of unused objects in the end of Modelling
-- 13. Delete any SubCategory that has not any corresponding SubCategoryVersion
delete sc 
from subcategory sc where not exists (select scv.subcategoryid from subcategoryversion scv where scv.subcategoryid=sc.SubCategoryID)


  -- 16. Delete any Item that is a Property but for which there does not exist any entry in the table: 
  -- Property with PropertyID=ItemID
delete from Item 
where IsProperty=1 and not exists (select * from Property where Property.PropertyID=Item.ItemID)


-- 16b. Delete any Property (and corresponding Item) for which there does not exist any PropertyCategory assignment
delete from Item 
where IsProperty=1 and not exists (select pc.* from PropertyCategory pc where pc.PropertyID=Item.ItemID)


-- 16c. Delete any Item (including Property) for which thre does not exist any ItemCategory assignment
delete from Item 
where not exists (select ic.* from ItemCategory ic where ic.ItemID=Item.ItemID)



-- 19. Delete all records for which NewCellID is not present in the TableVersionCells table for NewTableVID
delete cm from Aux_CellMapping cm where not exists 
(select tvc.* from tableversioncell tvc where tvc.tablevid=cm.NewTableVID and tvc.CellID=cm.NewCellID)

delete cs from Aux_CellStatus cs where not exists 
(select tvc.* from tableversioncell tvc where tvc.tablevid=cs.TableVID and tvc.CellID=cs.CellID)


-- 22. Delete any eventual Duplicate occurrences of TableRelation and RelatedConcep for relaitons of type 'header_attributeHeader'
-- First of all identify any duplicate conceptrelations
  DROP TABLE IF EXISTS #DuplicateConceptRelations 

  SELECT DISTINCT cr.ConceptRelationID 
  INTO #DuplicateConceptRelations
  FROM relatedConcept rc INNER JOIN ConceptRelation cr on rc.ConceptRelationID=cr.ConceptRelationID 
  INNER JOIN relatedConcept rc1 on rc1.ConceptRelationID=cr.ConceptRelationID 
  WHERE cr.Type='header_attributeHeader' 
  AND rc.IsRelatedConcept = 0 
  AND rc1.IsRelatedConcept = 1 
  AND EXISTS    (SELECT cr2.ConceptRelationID 
				 FROM   [RelatedConcept] rc2	
				 JOIN   [RelatedConcept] rc3	on rc3.ConceptGUID = rc.ConceptGUID and rc3.IsRelatedConcept = 0 and rc3.ConceptRelationID = rc2.ConceptRelationID 
				 JOIN   [ConceptRelation] cr2	on cr2.ConceptRelationID = rc2.ConceptRelationID and cr2.Type='header_attributeHeader' 
  				 WHERE  cr2.ConceptRelationID < cr.ConceptRelationID 
				 AND rc2.ConceptGUID = rc1.ConceptGUID and rc2.IsRelatedConcept = 1 
				)

-- Now delete RelatedConcept first and thereafter ConceptRelation
DELETE rc 
FROM RelatedConcept rc 
WHERE rc.ConceptRelationID in (select dc.ConceptRelationID from #DuplicateConceptRelations dc) 

DELETE cr 
FROM ConceptRelation cr   
WHERE cr.ConceptRelationID in (select dc.ConceptRelationID from #DuplicateConceptRelations dc) 


/*
-- THESE CLEAN ACTIONS CAN BE KEPT FOR THE PUBLICATION STAGE ONLY

-- 14. This needs a significant code to run effectively
-- Delete any Property that is not used by any: 
-- ContextComposition, TableVersion, HeaderVersion, VariableVersion or even SubCategoryItem itself (as a member of a Property Hierarchy)
CREATE TABLE #Props (PropertyID int)

INSERT INTO #Props
SELECT DISTINCT cc.propertyid 
FROM   contextcomposition cc

CREATE INDEX tmpIndxProps ON #Props (PropertyID)

INSERT INTO #Props
SELECT hv.propertyid 
FROM   headerversion hv 
WHERE  hv.propertyid is not null
AND NOT EXISTS (SELECT null 
                FROM   #Props p
                WHERE  p.PropertyID = hv.PropertyID)

INSERT INTO #Props
SELECT tv.propertyid 
FROM   tableversion tv 
WHERE  tv.propertyid is not null
AND NOT EXISTS (SELECT null 
                FROM   #Props p
                WHERE  p.PropertyID = tv.PropertyID)

 
INSERT INTO #Props
SELECT vv.propertyid 
FROM   variableversion vv
WHERE  NOT EXISTS (SELECT null 
                   FROM   #Props p
                    WHERE  p.PropertyID = vv.PropertyID)

INSERT INTO #Props
SELECT sci.Itemid 
FROM   SubCategoryItem sci 
WHERE  NOT EXISTS (SELECT null 
                   FROM   #Props p
                    WHERE  p.PropertyID = sci.ItemID)

DELETE p
FROM  property p
WHERE NOT EXISTS (SELECT p2.PropertyID
                           FROM   #Props p2 
						   WHERE p.PropertyID=p2.PropertyID
                          )
AND (not exists (select pc.* from PropertyCategory pc where pc.PropertyID=p.PropertyID and pc.StartReleaseID<>@CurrentRelease))
DROP TABLE #Props


  -- DECLARE @CurrentRelease int = 2
-- 15. Delete any Item that is not a Property and is not used by any: ContextComposition, SubCategoryItem

 -- First delete such an Item from any eventual CompoundItemContext entry if that item was a compound
delete cic from CompoundItemContext  cic inner join Item it on cic.ItemID=it.ItemID 
where it.IsProperty=0 and 
(not exists (select cc.itemid from contextcomposition cc where cc.ItemID=it.ItemID)) and 
not exists (select sci.itemid from subcategoryitem sci where sci.ItemID=it.ItemID) AND 
(not exists (select ic.* from ItemCategory ic where ic.ItemID=it.ItemID and ic.StartReleaseID<>@CurrentRelease)) AND 
(not exists (select ic.* from ItemCategory ic where ic.ItemID=it.ItemID and ic.IsDefaultItem=1)) 


-- Secondly delete the Item itself
delete it from item it 
where it.IsProperty=0 and 
(not exists (select cc.itemid from contextcomposition cc where cc.ItemID=it.ItemID)) and 
not exists (select sci.itemid from subcategoryitem sci where sci.ItemID=it.ItemID) AND 
(not exists (select ic.* from ItemCategory ic where ic.ItemID=it.ItemID and ic.StartReleaseID<>@CurrentRelease)) AND 
(not exists (select ic.* from ItemCategory ic where ic.ItemID=it.ItemID and ic.IsDefaultItem=1)) 


-- 17. Delete any Category that is not used by any: SubCategory, PropertyCategory, ItemCategory, SuperCategory
delete c 
from category c 
where 
(not exists (select sc.categoryid from subcategory sc where sc.CategoryID=c.CategoryID)) and 
(not exists (select pc.categoryid from propertycategory pc where pc.CategoryID=c.CategoryID)) and 
(not exists (select ic.categoryid from itemcategory ic where ic.CategoryID=c.CategoryID)) and 
(not exists (select scc.categoryid from supercategorycomposition scc where scc.CategoryID=c.CategoryID)) and 
(not exists (select scc.categoryid from supercategorycomposition scc where scc.SuperCategoryID=c.CategoryID))



-- 18. Delete any Framework that has not any existing corresponding Module.
delete
from Framework where frameworkid not in (select m.frameworkid from module m)



-- 20. Set EndRelease=CurrentRelease to all TableVersions that used to have EndRelease=Null but are not employed by any ModuleVersion with EndRelease=Null
update tv 
set tv.EndReleaseID=@CurrentRelease
from TableVersion tv 
where tv.EndReleaseID is Null 
and not exists (select * from ModuleVersionComposition mvc 
                inner join ModuleVersion mv on mv.ModuleVID=mvc.ModuleVID 
                where  tv.TableVID=mvc.TableVID and mv.EndReleaseID is Null 
               )



-- 21. Set EndRelease=CurrentRelease to all HeaderVersions that used to have EndRelease=Null but are not employed by any TableVersion (through TableVersionHeader) with EndRelease=Null
-- DECLARE @CurrentRelease int = 2
update hv 
set hv.EndReleaseID=@CurrentRelease
from HeaderVersion hv 
where hv.EndReleaseID is Null 
and not exists (select * from TableVersionHeader tvh 
                inner join TableVersion tv on tvh.TableVID=tv.TableVID 
                where  hv.HeaderVID=tvh.HeaderVID and tv.EndReleaseID is Null 
               )

*/

DROP TABLE IF EXISTS #DuplicateConceptRelations 

END