
BEGIN 


  IF OBJECT_ID(N'dbo.VarGeneration_Detail', N'U') IS NULL 
  CREATE TABLE dbo.VarGeneration_Detail  
     (   noofcells int,
		 NewAspect nvarchar(40),
		 ModuleVID int, 
		 ModuleCode nvarchar(50), 
		 TableCode nvarchar(50), 
		 TableVID int, 
		 CellID int, 
		 cellcode nvarchar(40), 
		 outcomeID nvarchar(10),
		 outcomeVID nvarchar(10),
		 ReportMsg nvarchar(1000),
		 isVoid bit, 
		 tvstartReleaseID int, 
		 mvStartReleaseID int, 
		 vvOldEndReleaseID int, 
		 OldAspect nvarchar(40), 
		 IsNewCell bit, 
		 isnewPropertyDataType bit, 
		 isNewKey bit, 
		 OldVariableID int,
		 NewVarID int,
		 OldVariableVID int,
		 NewVVID int
    );

  DELETE FROM dbo.VarGeneration_Detail
  
		   
  IF OBJECT_ID(N'dbo.VarGeneration_Summary', N'U') IS NULL CREATE TABLE dbo.VarGeneration_Summary  
  (outcomeid nvarchar(20), 
   outcomevid nvarchar(20), 
   ReportMsg nvarchar(1000), 
   noofcells int,  
   mincell nvarchar(100), 
   maxcell nvarchar(100)
  );

  DELETE FROM VarGeneration_Summary

  declare @maxContextID int  
  declare @maxKeyID int 
  declare @maxItemID int 
  declare @maxVariableID int 
  declare @maxVariableVID int 
  DECLARE @CurrentRelease int; --- = 1020000001
  
  --- DJT Added to make CurrentRelease dynamic
    SELECT @CurrentRelease = ReleaseID
  FROM   [dbo].[Release]
  WHERE  IsCurrent = 1;


  -- Retrieve "CurrentOwnerID and "CurrentOwnerAcronym from isCurrent release. Default values are 1012 & eba.
  DECLARE @tempOwnerID int = (SELECT max(co.OwnerID) FROM Concept co INNER JOIN Release r ON co.ConceptGUID=r.RowGUID WHERE r.isCurrent=1);
  DECLARE @CurrentOwnerID int = ISNULL(@tempOwnerID, 1012);
  DECLARE @CurrentOwnerAcronym nvarchar(50) = (SELECT lower(max(Acronym)) from Organisation where OrgID=@CurrentOwnerID) 
  --Select @CurrentOwnerAcronym

  Update ic 
  Set Signature = @CurrentOwnerAcronym + '_' + c.Code + ':' + ic.Code 
  FROM ItemCategory ic INNER JOIN Category c on ic.CategoryID=c.CategoryID 
  INNER JOIN Item it on ic.ItemID=it.ItemID 
  WHERE it.isProperty=0 and ic.EndReleaseID is Null AND ic.StartReleaseID  = @CurrentRelease

  Update ic 
  Set Signature = ic.Code 
  FROM ItemCategory ic   INNER JOIN Item it on ic.ItemID=it.ItemID 
  WHERE it.isProperty=1 and ic.EndReleaseID is Null AND ic.StartReleaseID  = @CurrentRelease


  --select * from itemcategory ic   WHERE ic.EndReleaseID is Null AND ic.StartReleaseID  = @CurrentRelease


  -- Now is time to check that if a HeaderVersion created in CurrentRelease is identical to a HeaderVersion created in previous release, then revert to the previous HeaderVersion
  -- First identify such HeaderVersions
  --declare @CurrentRelease int = 1010000009  
  DROP TABLE IF EXISTS #SameHeaderVersions
  SELECT DISTINCT tv.TableVID, hv.HeaderID, hv.HeaderVID as NewHeaderVID, hv2.HeaderVID as OldHeaderVID
  INTO #SameHeaderVersions
  		 FROM [TableVersion]		tv 
		 JOIN [Table]				t	ON (t.TableID		= tv.TableID) 
         JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
         JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
		 JOIN [Header]				h	ON (t.TableID		= h.TableID) 
		 JOIN [HeaderVersion]		hv	ON (h.HeaderID		= hv.HeaderID) 
		 JOIN [TableVersionHeader]	tvh ON (
											tv.TableVID		= tvh.TableVID 
										  AND 
										    tvh.HeaderID	= h.HeaderID
										   ) 
		 JOIN [HeaderVersion]		hv2 ON (hv2.HeaderID	= h.HeaderID)
  WHERE t.IsAbstract		= 0 
  AND   tv.EndReleaseID		IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND   h.isKey				= 0 
  AND   tvh.isAbstract		= 0 
  AND   hv.EndReleaseID		IS NULL 
  AND   hv2.EndReleaseID	= hv.StartReleaseID 
  AND   ISNULL(hv.Code,'-111111111')=ISNULL(hv2.Code ,'-111111111')
  AND   ISNULL(hv.Label,'-111111111')=ISNULL(hv2.Label ,'-111111111')
  AND   ISNULL(hv.ContextID,-999999999)=ISNULL(hv2.ContextID ,-999999999)
  AND   ISNULL(hv.PropertyID,-999999999)=ISNULL(hv2.PropertyID ,-999999999)
  AND   ISNULL(hv.SubCategoryVID,-999999999)=ISNULL(hv2.SubCategoryVID ,-999999999)
  ORDER BY tv.TableVID, hv.HeaderVID;

  -- Change TableVersionHeaders 
  UPDATE tvh 
  SET tvh.HeaderVID=shv.OldHeaderVID  
  FROM [TableVersionHeader] tvh 
  INNER JOIN #SameHeaderVersions shv ON tvh.TableVID=shv.TableVID AND tvh.HeaderID=shv.HeaderID 
  WHERE tvh.HeaderVID=shv.NewHeaderVID 

  --Delete all HeaderVersions with NewHeaderVID as redudndatnt
  DELETE hv 
  FROM HeaderVersion hv 
  INNER JOIN #SameHeaderVersions shv ON hv.HeaderVID=shv.NewHeaderVID 

  -- Set to all OldHeaderVersions EndRelease=Null
  UPDATE hv 
  SET hv.EndReleaseID = NULL
  FROM HeaderVersion hv 
  INNER JOIN #SameHeaderVersions shv ON hv.HeaderVID=shv.OldHeaderVID 
  
  
-- 	If there are Modelling Errors THEN: STOP Variable Generation AND review the Modelling of the corresponding TableVersion(s).
execute [dbo].[check_modelling_rules_tidy]

--Correct Version: IF 1 in (SELECT isBlocking FROM ModelViolations) 
-- "2" IS SET TO BE ABLE TO KEEP RUNNING  Var Generaiton for testing purposes when some Violaitons are there
IF 1 in (SELECT isBlocking FROM ModelViolations) 
  PRINT 'Violations Found: Variable Generation cannot Proceed'

ELSE
-- VI.	ELSE (If there are no modelling errors), the tool prepares a list of cells in the new table versions (EndRelease = null) 
--      in the modules with (startRelease = CurrentRelease)with the relevant information. 
-- For reasons of reporting AND comparisons, we will include INTO this table, all the Cells FROM all Tables FROM all ModuleVersions WHERE ModuleVersion.EndReleaseID=null

BEGIN


-- CLEANING STAGE: All Variables where vv.STartRelease=CurrentrELEASE HAVE TO BE CELANED AND ALL FOREIGN KEYS WOULD BE CLEANED FIRST.

-- Clean Cell Status for non-existing Cells there
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012; declare @maxContextID int; declare @maxKeyID int; declare @maxItemID int; declare @maxVariableID int; declare @maxVariableVID int 
DELETE cst FROM Aux_CellStatus cst 
WHERE NOT EXISTS (SELECT * FROM TableVersionCell tvc WHERE tvc.CellID=cst.CellID AND tvc.TableVID=cst.TableVID ) 

-- Clean all ModuleParameters entries for ModuleVIDs where ModuleVersion.StartRelease=CurrentRelease
DELETE mp 
FROM ModuleParameters mp INNER JOIN ModuleVersion mv ON mp.ModuleVID=mv.ModuleVID 
WHERE mv.STartReleaseID=@CurrentRelease OR mv.STartReleaseID=9999


-- CLEAN everything if in the KeyComposition there is KeyVariable with StartRelease=CurrentRelease
-- First clean ModuleVersion.GlobalKeyID
UPDATE mv 
SET mv.GlobalKeyID=NULL 
FROM ModuleVersion mv
WHERE mv.GlobalKeyID in 
(SELECT kc.KeyID FROM KeyComposition kc WHERE kc.VariableVID in (SELECT vv.VariableVID FROM VariableVersion vv WHERE vv.StartReleaseID=@CurrentRelease OR vv.STartReleaseID=9999))


-- clean TableVersion.KeyID
UPDATE tv 
SET tv.KeyID=NULL 
FROM TableVersion tv
WHERE tv.StartReleaseID=@CurrentRelease OR tv.StartReleaseID=9999


-- clean HeaderVersion.KeyVariableVID
UPDATE hv 
SET hv.KeyVariableVID = NULL 
FROM HeaderVersion hv
WHERE hv.StartReleaseID=@CurrentRelease  OR hv.StartReleaseID=9999
--and hv.KeyVariableVID in (SELECT vv.VariableVID FROM VariableVersion vv WHERE vv.StartReleaseID=@CurrentRelease)



--  	WHEN the button “Variable Generation” is clicked: Clean VariableVID for the cells in all the TableVersions (with TableVersion.StartRelease=CurrentRelease) 
--      of the ModuleVersions with TableVersion.StartRelease = CurrentRelease.
  UPDATE tvc 
  SET    VariableVID = NULL 
  FROM   [TableVersionCell]		  	  tvc  
  JOIN   [TableVersion] 			  tv  ON (tv.TableVID  = tvc.TableVID)
  JOIN   [ModuleVersionComposition]   mvc ON (mvc.TableVID = tv.TableVID) 
  JOIN   [ModuleVersion] 			  mv  ON (mv.ModuleVID = mvc.ModuleVID)
  WHERE  (mv.StartReleaseID = @CurrentRelease  OR mv.STartReleaseID=9999)
  AND    (tv.StartReleaseID = @CurrentRelease OR tv.STartReleaseID=9999);


--declare @CurrentRelease int = 2
-- Clean CompoundKeys (and cascade to keycomposiitons with Key Variables whose StartRelease=Current Release
-- First set relevant vv.KeyID=null
UPDATE vv 
SET vv.KeyID=Null
FROM VariableVersion vv 
WHERE vv.KeyID in (SELECT kc.KeyID FROM KeyComposition kc WHERE kc.VariableVID in (SELECT vv.VariableVID FROM VariableVersion vv WHERE vv.StartReleaseID=@CurrentRelease OR vv.STartReleaseID=9999))

-- Secondly set relevant tv.KeyID=null
UPDATE tv 
SET tv.KeyID=Null
FROM TableVersion tv 
WHERE tv.KeyID in (SELECT kc.KeyID FROM KeyComposition kc WHERE kc.VariableVID in (SELECT vv.VariableVID FROM VariableVersion vv WHERE vv.StartReleaseID=@CurrentRelease OR vv.STartReleaseID=9999))

-- Third set to all relevant HeaderVersions hv.KeyVariableVID=Null
UPDATE hv 
SET hv.KeyVariableVID=Null
FROM HeaderVersion hv 
WHERE hv.KeyVariableVID in (SELECT vv.VariableVID FROM VariableVersion vv WHERE vv.StartReleaseID=@CurrentRelease OR vv.STartReleaseID=9999)

-- Now delete CompoundKey & Cascade to KeyComposition
DELETE ck 
FROM CompoundKey ck 
WHERE ck.KeyID IN 
(SELECT kc.KeyID FROM KeyComposition kc WHERE kc.VariableVID in (SELECT vv.VariableVID FROM VariableVersion vv WHERE vv.StartReleaseID=@CurrentRelease OR vv.STartReleaseID=9999))


-- Now go to deleting all VariableVersions
-- Before cleaning VariableVersions with StartRelease=CurrentRelease, set prev_VV_EndRelease=Null 
UPDATE vv 
SET vv.EndReleaseID = NULL 
FROM VariableVersion vv 
WHERE (vv.EndReleaseID=@CurrentRelease  OR vv.EndReleaseID=9999) AND 
vv.VariableID in (SELECT vv.VariableID FROM VariableVersion vv WHERE (vv.StartReleaseID=@CurrentRelease OR vv.STartReleaseID=9999))


-- Now Delete Variabl;eVersion with StartRelease=CurrentRelease 
DELETE vv 
FROM VariableVersion vv 
WHERE StartReleaseID=@CurrentRelease  OR vv.STartReleaseID=9999

-- Remove VariableID references from OperandReference records if not exists relevant vv
UPDATE orf
SET orf.VariableID = Null 
FROM OperandReference orf  
WHERE NOT EXISTS (SELECT vv.* FROM VariableVersion vv WHERE vv.VariableID=orf.VariableID)


-- Finally Delete any VariableID without VariableVersions on it
DELETE v 
FROM Variable v 
WHERE NOT EXISTS (SELECT vv.* FROM VariableVersion vv WHERE vv.VariableID=v.VariableID)


-- declare @CurrentRelease int = 1010000009
-- IDENTIFICATION OF KEY VARIABLES
-- 1. For each Header.isKey=1 AND the relevant HeaderVersion, identify a Key Variable with VariableVersion.Property = HeaderVersionProperty 
--    AND VariableVersion.EndRelease=Null.
--    Non existing Key Variables for some Properties must be identified so AS afterwards to INSERT New such Variables

--- Add check to prevent error if table doesn't exist

  DROP TABLE IF EXISTS #non_existing_keyproperties; 
 

  SELECT DISTINCT 
		 hv.PropertyID 
  INTO 	 #non_existing_keyproperties
  FROM   [HeaderVersion] 				hv 
  JOIN   [Header] 						h 	ON (hv.HeaderID  = h.HeaderID) 
  JOIN   [TableVersionHeader] 			tvh ON (tvh.HeaderVID = hv.HeaderVID)
  JOIN   [TableVersion] 				tv 	ON (tvh.TableVID = tv.TableVID) 
  JOIN   [ModuleVersionComposition] 	mvc ON (mvc.TableVID = tv.TableVID)
  JOIN   [ModuleVersion] 				mv 	ON (mv.modulevid = mvc.ModuleVID)
  WHERE  mv.StartReleaseID = @CurrentRelease 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND    h.IsKey 		   = 1 
  AND    hv.propertyid NOT IN (SELECT vv.propertyid 
						       FROM   [VariableVersion] vv 
							   JOIN   [Variable] 	    v   ON (v.VariableID = vv.VariableID) 
							   WHERE  v.Type='key' AND vv.EndReleaseID is null 
						      );

---
---
  DROP TABLE IF EXISTS #InsertVar
  CREATE TABLE #InsertVar (VariableID int, PropertyID int);

  -- SET IDENTITY_INSERT [Variable] ON;
  DECLARE @maxivvar INT = (SELECT ISNULL(max(VariableVID),1010000000) FROM [VariableVersion] where VariableVID>=1010000000)
   MERGE Variable AS v
  USING  (SELECT (@maxivvar + ROW_NUMBER() OVER (ORDER BY PropertyID)) newVarId,
		          'key' NewType ,
				  PropertyID
		  FROM #non_existing_keyproperties
		 ) AS nek(VariableID, [Type], PropertyID) 
  ON     (v.VariableID = nek.VariableID)
  WHEN NOT MATCHED THEN
     INSERT (VariableID, Type, OwnerID) 
	 VALUES (nek.VariableID, nek.[Type], @currentOwnerID)
     OUTPUT Inserted.VariableID, nek.PropertyID
     INTO   #InsertVar;
  
  -- SET IDENTITY_INSERT [Variable] OFF;

  -- SET IDENTITY_INSERT [VariableVersion] ON;
  
  INSERT INTO [VariableVersion] (VariableVID, VariableID, PropertyID, StartReleaseID)  
  SELECT iv.VariableID,
		 iv.VariableID, 
		 iv.PropertyID,
		 @CurrentRelease
  FROM   #InsertVar iv;

  -- SET IDENTITY_INSERT [VariableVersion] OFF;
  
-- 3.	Assign HeaderVersion.KeyVariableVID to this specific VariableVersion
-- declare @CurrentRelease int = 1010000009
  UPDATE hv
  SET    hv.KeyVariableVID = vv.VariableVID 
  FROM   [HeaderVersion]   hv 
  JOIN   [Header] h			  ON (hv.HeaderID   = h.HeaderId)
  JOIN   [VariableVersion] vv ON (vv.PropertyID = hv.PropertyID)
  JOIN   [Variable]        v  ON (v.VariableID  = vv.VariableID) 
  WHERE  v.type        = 'key' 
  AND h.IsKey = 1
  AND vv.EndReleaseID is Null 
  AND hv.StartReleaseID=@CurrentRelease;
  
  DROP TABLE IF EXISTS #non_existing_keyproperties;

-- Generation of Table Keys (after Identification of Key Variables)
--
-- 1.	For a TableVersion collect all Headers WHERE isKey=1 that appear to this TableVersionHeader AND identify their KeyVariableIVID.

  DROP TABLE IF EXISTS #tablekeys;
  
  DROP TABLE IF EXISTS #tablekeycomposition;

  DROP TABLE IF EXISTS #non_existing_keysignatures;
 --declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;
  SELECT DISTINCT 
		 tv.TableVID, 
		 hv.PropertyID, 
		 hv.KeyVariableVID 
  INTO   #tablekeycomposition 
  FROM   [HeaderVersion] 			hv 
  JOIN   [Header] 		 			h 	ON (hv.HeaderID  = h.HeaderID)
  JOIN   [TableVersionHeader] 		tvh ON (tvh.HeaderID = h.HeaderID)
  JOIN   [TableVersion] 			tv 	ON (tvh.TableVID = tv.TableVID)
  JOIN   [ModuleVersionComposition] mvc ON (mvc.TableVID = tv.TableVID)
  JOIN   [ModuleVersion] 			mv 	ON (mv.modulevid = mvc.ModuleVID)
  WHERE  mv.StartReleaseID = @CurrentRelease 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND    hv.EndReleaseID IS NULL
  AND    h.IsKey = 1
  ; 
  

--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;
   SELECT DISTINCT 
         tv.TableVID,
		 STRING_AGG(CAST(tk2.PropertyID AS nvarchar), '#') WITHIN GROUP (ORDER BY tk2.PropertyID) + '#' AS [Signature]
  INTO   #tablekeys 
  FROM   [TableVersion] 			tv
  JOIN   [#tablekeycomposition]     tk2 ON (tk2.TableVID = tv.TableVID)
  JOIN   [ModuleVersionComposition] mvc ON (mvc.TableVID = tv.TableVID) 
  JOIN   [ModuleVersion] 			mv  ON (mv.ModuleVID = mvc.ModuleVID)
  WHERE  mv.StartReleaseID = @CurrentRelease 
  AND    tv.StartReleaseID = @CurrentRelease 
  GROUP BY tv.TableVID
  
  DELETE tk
  FROM   #tablekeys tk
  WHERE  tk.Signature IS NULL;

-- SELECT * FROM #tablekeys

-- 2.	Identify if this Combination of Key Variables is existing in any CompoundKey AS its KeyComposition.
--declare @CurrentRelease int = 1010000009
  SELECT DISTINCT 
         tk.[signature] 
  INTO   #non_existing_keysignatures
  FROM   #tablekeys tk
  WHERE  tk.[signature] NOT IN (SELECT ck.[signature] 
							    FROM   CompoundKey ck
							   )
  AND    ISNULL(tk.[signature],'') != '';

  
-- 3.	If this Combination is NOT already existing in a CompoundKey: 
--      INSERT a New Compound Key object. 
--      For every Key HeaderID of this TableVersionHeader, 
--        INSERT the HeaderVersion.KeyVariableVID AS each component of the KeyComposiiton table for the newly created CompoundKey.KeyID.
--

  set @maxKeyID = isNull((select max(KeyID) from CompoundKey where KeyID>=1010000000),1010000000)
  INSERT INTO CompoundKey ([KeyID], [Signature], [OwnerID])
  SELECT distinct	 @maxKeyID + ROW_NUMBER() OVER(ORDER BY #non_existing_keysignatures.[Signature] ASC) AS KeyID 
					,[Signature] 
					,@CurrentOwnerID
  FROM   #non_existing_keysignatures
  WHERE NOT EXISTS (Select * from CompoundKey ck2 WHERE ck2.[Signature]=#non_existing_keysignatures.[Signature]) ;
  
  INSERT INTO KeyComposition (KeyID, VariableVID)
  SELECT DISTINCT 
		 ck.KeyID, 
		 tkc.KeyVariableVID
  FROM   [CompoundKey] 				 ck 
  JOIN   #tablekeys 				 tk  ON (ck.Signature  = tk.Signature) 
  JOIN   #non_existing_keysignatures nex ON (nex.Signature = tk.Signature) 
  JOIN   #tablekeycomposition 		 tkc ON (tk.TableVID   = tkc.TableVID) 
  WHERE  tkc.KeyVariableVID IS NOT NULL 
  AND    NOT EXISTS (SELECT kc2.* 
		 			 FROM   KeyComposition kc2 
		 			 WHERE  kc2.KeyID       = ck.KeyID 
		 			 AND    kc2.VariableVID = tkc.KeyVariableVID
		 		    );

-- 4.	Assign TableVersion.KeyID=CompoundKey.KeyID.
  UPDATE tv 
  SET    KeyID = ck.KeyID 
  FROM   [TableVersion] 			 tv
  JOIN   #tablekeys 				 tk  ON (tk.TableVID   = tv.TableVID) 
  JOIN   [CompoundKey] 				 ck  ON (ck.Signature  = tk.Signature) 
  WHERE tv.StartReleaseID=@CurrentRelease



   DROP TABLE IF EXISTS #tablekeys;
   DROP TABLE IF EXISTS #tablekeycomposition;
   DROP TABLE IF EXISTS #non_existing_keysignatures;



-- NOW GENERATE FILING INDICATOR VARIABLES


--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;
--1.	Collect All Distinct Filing Indicators which do not already exist as “Items”.
--a.	A Filing Indicator is the TableVerison.Code (with tv.EndRelease=Null) for a TableVersion where AbsrtactTableID=Null OR AbstractTable.TableVersion.Code for a table where AbstractTableID isw not Null.
DROP TABLE IF EXISTS #FICodes;
DROP TABLE IF EXISTS #FITable;


SELECT DISTINCT trim(CASE WHEN tv2.TableVID is not NULL THEN tv2.Code ELSE tv.Code END) as FilingIndicatorCode 
INTO #FICodes
FROM TableVersion tv LEFT OUTER JOIN TableVersion tv2 ON tv.AbstractTableID=tv2.TableID
WHERE 
tv.EndReleaseID is NULL AND
tv2.EndReleaseID is NULL;


-- b.	A non-existing FilingIndicator is one in which It Does Not exist a Record in ItemCategory table with: Code=FilingIndicatorCode & EndRelease=Null & Category.Name=”Template”
--      and also this Filing Indicator exists in one ModuleVersionComposition entry where ModuleVersion.StartRelease=CurrentRelease.
-- 2.	Number the above FilingIndicators in ascending Order 
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;
SELECT 
  ROW_NUMBER() OVER(ORDER BY fi.FilingIndicatorCode ASC) AS FID,
  fi.FilingIndicatorCode, 0 as ispreexisting
INTO #FITable
FROM 
#FICodes fi 
WHERE 
fi.FilingIndicatorCode IN (SELECT trim(CASE WHEN tv2.TableVID is not NULL THEN tv2.Code ELSE tv.Code END) as Code 
							  FROM TableVersion tv LEFT OUTER JOIN TableVersion tv2 ON tv.AbstractTableID=tv2.TableID 
							  INNER JOIN ModuleVersionComposition mvc ON tv.TableVID=mvc.TableVID 
							  INNER JOIN ModuleVersion mv ON mv.ModuleVID=mvc.ModuleVID 
							  WHERE tv.EndReleaseID is Null AND tv2.EndReleaseID is NULL AND mv.StartReleaseID=@CurrentRelease 
								)                         

--select * from #FITable

--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;  declare @maxitemid int 

-- 3.	Create Items for each of the above Filing Indicators
set @maxItemID = ISNULL((select max(ItemID) from Item where itemID>=1012420000),1012420000)

-- SET IDENTITY_INSERT [Item] ON
INSERT INTO Item (ItemID, Name, isProperty, isActive, OwnerID)
SELECT ISNULL(@maxItemID,0)+ROW_NUMBER() OVER (ORDER BY fi.FID) as ItemID, fi.FilingIndicatorCode, 0 as isProperty, 1 as isActive, @CurrentOwnerID   
FROM #FITable  fi 
WHERE fi.FilingIndicatorCode NOT IN (SELECT trim(ic.Code) 
									 FROM ItemCategory ic INNER JOIN Category c ON ic.CategoryID=c.CategoryID 
									 WHERE ic.EndReleaseID is NULL AND c.Name='Templates'
									)
-- SET IDENTITY_INSERT [Item] OFF

--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;  declare @maxitemid int 
-- 4.	Create ItemCategories for each of the above Filing Indicators
INSERT INTO ItemCategory (ItemID, CategoryID, Code, isDefaultItem, [Signature], StartReleaseID, EndReleaseID)
SELECT ISNULL(@maxItemID,0)+ROW_NUMBER() OVER (ORDER BY fi.FID) as ItemID, c.CategoryID, fi.FilingIndicatorCode as Code, 0 as isDefaultItem, 
'eba__TE:' + fi.filingindicatorcode as [Signature], @CurrentRelease as StartReleaseID, Null as EndRelease  
FROM #FITable fi, Category c 
WHERE c.CategoryID in (SELECT c2.CategoryID FROM Category c2 WHERE c2.Name='Templates') and 
fi.FilingIndicatorCode NOT IN (SELECT trim(ic.Code) 
									 FROM ItemCategory ic INNER JOIN Category c2 ON ic.CategoryID=c2.CategoryID 
									 WHERE ic.EndReleaseID is NULL AND c2.Name='Templates'
)

-- NEW STEP: Update any filingindicators from ItemCategory if StartRelease=9999 to @CurrwntRelease
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;  
UPDATE ic 
SET ic.StartReleaseID=@CurrentRelease 
--select *
FROM ItemCategory ic 
JOIN #FICodes fi ON trim(fi.FilingIndicatorCode)=trim(ic.Code)
WHERE ic.StartReleaseID=9999 AND ic.EndReleaseID is NULL


--select * from item where itemid between 1010000000 and 101999999
--select * from itemcategory where itemid between 1010000000 and 101999999


-- 5.	Create Contexts for each of the above Filing Indicators
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;  declare @maxcontextid int; 
set @maxcontextid = (select ISNULL(max(ContextID),1010000000) from Context where ContextID>=1010000000) 
-- SET IDENTITY_INSERT [Context] ON
INSERT INTO Context (ContextID, [Signature], OwnerID)
SELECT ISNULL(@maxContextID,1010000000)+ROW_NUMBER() OVER (ORDER BY fi.FID) as ContextID, 
trim(str(p.ItemID))+'_'+trim(str((SELECT max(ic.ItemID) from ItemCategory ic WHERE ic.CategoryID=1004 and ic.EndReleaseID is NULL and ic.Code=FI.FilingIndicatorCode)))+'#', @CurrentOwnerID  
FROM #FITable fi, Item p
WHERE p.Name='Template' and 
NOT EXISTS (select * from Context cx2 where cx2.
Signature=trim(str(p.ItemID))+'_'+
          trim(str((SELECT max(ic.ItemID) from ItemCategory ic WHERE ic.CategoryID=1004 and ic.EndReleaseID is NULL and ic.Code=FI.FilingIndicatorCode)))+'#') 
AND NOT EXISTS (select * 
from ContextComposition cc inner join Item p2 on p2.ItemID=cc.PropertyID inner join ItemCategory ic on ic.ItemID=cc.ItemID 
WHERE p2.Name='Template' AND ic.Code=fi.FilingIndicatorCode and ic.EndReleaseID is Null 
and 1=(select count(cc2.propertyid) from contextcomposition cc2 where cc2.contextid=cc.contextid)) 

--select * from context where signature like '1012400922_%' order by contextid desc


-- SET IDENTITY_INSERT [Context] OFF

-- 6.	Create ContextCompositions for each of the above Filing Indicators 
--      with Property= the property with Item.Name=’Template’ and Item, the Item with ItemCategory.Code=FilingIndicatorCode, 
--      EndRelease=Null and Category.Name=’Templates’
INSERT INTO ContextComposition (ContextID, PropertyID, ItemID)
SELECT DISTINCT cx.ContextID as ContextID, p.ItemID as ccPropertyID, (select max(ic3.ItemID) from ItemCategory ic3 where ic3.Code=fi.FilingIndicatorCode and ic3.EndReleaseID is null and ic3.CategoryID in (select c3.CategoryID from Category c3 where c3.Name='Templates')) as ccItemID
FROM #FITable fi, Item p, Context cx 
WHERE p.Name='Template' AND 
cx.Signature=trim(str(p.ItemID))+'_'+ltrim(str((select max(ic3.ItemID) from ItemCategory ic3 where ic3.Code=fi.FilingIndicatorCode and ic3.EndReleaseID is null and ic3.CategoryID in (select c3.CategoryID from Category c3 where c3.Name='Templates'))))+'#'
AND NOT EXISTS (select * 
from ContextComposition cc inner join Item p2 on p2.ItemID=cc.PropertyID inner join ItemCategory ic on ic.ItemID=cc.ItemID 
WHERE cc.ContextID=cx.ContextID AND p2.Name='Template' AND ic.Code=fi.FilingIndicatorCode and ic.EndReleaseID is Null 
and 1=(select count(cc2.propertyid) from contextcomposition cc2 where cc2.contextid=cc.contextid)) 


-- 7.	Create Variables for each of the above Filing Indicators with Variable.Type=’filingindicator’
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;  declare @maxvariableid int; 
set @maxVariableID = (select max(VariableID) from Variable WHERE VariableID>=1010000000) 
-- SET IDENTITY_INSERT [Variable] ON
INSERT INTO Variable (VariableID, [Type], OwnerID)
SELECT ISNULL(@maxVariableID,1010000000)+ROW_NUMBER() OVER (ORDER BY fi.FID )as VariableID, 'filingindicator' as vtype, @CurrentOwnerID as OwnerID  
FROM #FITable fi
WHERE NOT EXISTS (select * from Variable v2 INNER JOIN VariableVersion vv2 on v2.VariableID=vv2.VariableID 
                  WHERE v2.type='filingindicator' AND vv2.EndReleaseID is Null and vv2.Code=fi.FilingIndicatorCode)

-- SET IDENTITY_INSERT [Variable] OFF


-- 8.	Create VariableVersions for each of the above Filing Indicators, with: 
--      Code=FilingIndicatorCode, -  Property=The property with Item.Name=’isReported’, 
--      Context=The corresponding Context to Filing Indicator, StartRelease=CurrentRelease, EndRelease=Null.
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012;  declare @maxvariablevid int; 
set @maxVariableVID = (select max(VariableVID) from VariableVersion WHERE VariableVID>=1010000000) 
-- SET IDENTITY_INSERT [VariableVersion] ON
INSERT INTO VariableVersion (VariableVID, VariableID, Code, PropertyID, ContextID, StartReleaseID, EndReleaseID, isMultiValued)
SELECT ISNULL(@maxVariableVID,1010000000)+ROW_NUMBER() OVER (ORDER BY fi.FID) as VariableVID, 
ISNULL(@maxVariableID,1010000000)+ROW_NUMBER() OVER (ORDER BY fi.FID) as VariableID, 
fi.FilingIndicatorCode as Code, p.ItemID as PropertyID, 
(select max(cc.contextID) from ContextComposition cc where cc.PropertyID in (select it.ItemID from Item it where it.Name='Template')  
and cc.ItemID in (select max(ic3.ItemID) from ItemCategory ic3 where ic3.Code=fi.FilingIndicatorCode and ic3.EndReleaseID is null and ic3.CategoryID in (select c3.CategoryID from Category c3 where c3.Name='Templates'))) 
as ContextID, 
@CurrentRelease as StartReleaseID, Null as EndReleaseID, 0 as isMultiValued 
FROM #FITable fi, Item p
WHERE p.Name='isReported' AND 
NOT EXISTS (select * from Variable v2 INNER JOIN VariableVersion vv2 on v2.VariableID=vv2.VariableID 
            WHERE v2.type='filingindicator' AND vv2.EndReleaseID is Null and vv2.Code=fi.FilingIndicatorCode)


-- SET IDENTITY_INSERT [VariableVersion] OFF


-- 9.	For each New Filing Indicator and each TableVersion corresponding to this filingindicator (with endrelease=null) 
--      and each ModuleVersion (with startrelease=currentrelease and endrelease=null), 
--      for which there exists a ModuleVersionComposition entry with the pair (ModuleVID, TableVID), 
--      Assign to ModuleParameters Table a New Entry with the pair: (ModuleVID, corresponding VariableVID to that TableVID) 
--      if such pair does not preexist.
--declare @currentrelease int = 1010000009;      declare @currentownerid int = 1012; 
INSERT INTO ModuleParameters (ModuleVID, VariableVID)
SELECT distinct mv.ModuleVID, 
(select max(vv2.VariableVID) from VariableVersion vv2 inner join variable v2 on vv2.variableid=v2.VariableID where v2.type='filingindicator' and vv2.EndReleaseID is null and trim(vv2.Code)=trim(fi.FilingIndicatorCode) ) as VariableVID
FROM 
TableVersion tv
INNER JOIN ModuleVersionComposition mvc on mvc.TableVID=tv.TableVID 
INNER JOIN ModuleVersion mv on mvc.ModuleVID=mv.ModuleVID ,
#FITable fi
WHERE 
(
(tv.AbstractTableID is Null AND tv.Code=fi.FilingIndicatorCode)
OR 
(tv.AbstractTableID is NOT Null AND 
fi.FilingIndicatorCode IN (SELECT tv2.Code FROM TableVersion tv2 WHERE tv.AbstractTableID=tv2.TableID and tv2.EndReleaseID is Null)
)
)
AND 
mv.EndReleaseID is NULL and tv.EndReleaseID is NULL and mv.StartReleaseID=@CurrentRelease 
AND NOT EXISTS (SELECT * FROM ModuleParameters mp2 WHERE mp2.VariableVID=
(select max(vv2.VariableVID) from VariableVersion vv2 inner join variable v2 on vv2.variableid=v2.VariableID where v2.type='filingindicator' and vv2.EndReleaseID is null and trim(vv2.Code)=trim(fi.FilingIndicatorCode) )
AND mp2.ModuleVID=mv.ModuleVID )

--select count(distinct variablevid), @maxVariableVID, min(variablevid), max(variablevid) from ModuleParameters

DROP TABLE IF EXISTS #FICodes;
DROP TABLE IF EXISTS #FITable;


-- NOW PROCEED TO FACT VARIABLE GENERATION
  -- declare @currentrelease int = 2 
-- Preparatory Steps


-- II.	For all the above TableVersions, Run “Check Modelling Rules” again to check for any blocking modelling rule violations (i.e. modelling errors).
-- III.	If there are Modelling Errors THEN: STOP Variable Generation AND review the Modelling of the corresponding TableVersion(s).
-- IV.	ELSE (If there are no modelling errors), check the following additional modelling rules:
-- a.	For All Headers of a TableVersion in the ModuleVersion with StartRelease=CurrentRelease each PropertyID that is assigned to a SubCategoryVID must be assigned to a Unique SubCategoryVID



--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; declare @maxContextID int; declare @maxKeyID int; declare @maxItemID int; declare @maxVariableID int; declare @maxVariableVID int;  
  DROP TABLE IF EXISTS #cellmodelling;

  CREATE TABLE #cellmodelling (
  ModuleVID int, 
  ModuleCode nvarchar(30), 
  TableCode nvarchar(30), 
  TableVID int, 
  CellID int, 
  CellCode nvarchar(100), 
  IsVoid bit, 
  TvStartReleaseID int,  
  mvStartReleaseID int, 
  vvOldEndReleaseID int, 
  oldVariableID int, 
  oldVariableVID int,
  oldContextID int, 
  oldPropertyID int, 
  oldKeyID int, 
  oldAspect nvarchar(100), 
  newSignature nvarchar(2000), 
  newKeysignature nvarchar(2000), 
  newContextID int, 
  newPropertyID int, 
  newKeyID int, 
  newAspect nvarchar(100), 
  OutcomeID nvarchar(15),
  OutcomeVID nvarchar(15), 
  newVarID int, 
  newVVID int, 
  isNewCell bit, 
  isNewPropertyDataType bit, 
  isNewKey bit, 
  isNewTableVersion bit, 
  isNewModuleVersion bit, 
  isOtherID bit, 
  isOtherVVID bit, 
  newVVIDStartRelease int, 
  sameAspectAsPrevID bit,
  oldVVIDExistsInOtherCell bit, 
  oldIDExistsInOtherCell bit, 
  sameVVIDEXISTSiNOTherCellandNewMV bit, 
  sameIDEXISTSiNOTherCellandNewMV bit, 
  NotExistSameCellVVIDOrHasSameNewAspect bit,
  ExistsActiveSameAspect bit, 
  SameNewAspectExistsInOtherCellWithDiffOldVarID bit, 
  SameNewAspectExistsInOtherCellWithDiffOldVarIDInNewMV bit, 
  ReportMsg nvarchar(1000));

  -- DECLARE @CurrentRelease int = 2 --1020000001

  INSERT INTO #cellmodelling
  SELECT  mv.ModuleVID, 
		  mv.Code 			AS ModuleCode, 
		  tv.Code 			AS TableCode, 
		  tvc.TableVID, 
		  tvc.CellID, 
		  tvc.cellcode, 
		  (case when tvc.isVoid=1 or tvc.IsExcluded=1 then 1 else 0 end) as isVoid, 
		  tv.StartReleaseID AS tvstartReleaseID, 
		  mv.StartReleaseID AS mvStartReleaseID, 
		  vv.EndReleaseID 	AS vvOldENDReleaseID, 
		  vv.VariableID 	AS oldVariableID, 
		  vv.VariableVID 	AS oldVariableVID, 
		  vv.ContextID 		AS OldContextID, 
		  vv.PropertyID 	AS OldPropertyID, 
		  vv.KeyID 			AS OldKeyID, 
		 (CASE 
		    WHEN vv.keyid IS NULL THEN '' 
			ELSE CAST(vv.KeyID AS nvarchar) 
		  END) + '_' +  
		 (CASE 
		    WHEN vv.PropertyID IS NULL THEN '' 
			ELSE CAST(vv.PropertyID AS nvarchar) 
		  END) + '_' +
		 (CASE 
		    WHEN vv.ContextID IS NULL THEN '' 
			ELSE CAST(vv.ContextID AS nvarchar) 
		  END
		 ) 								AS OldAspect, 
		  '' 							AS NewSignature,
		  '' 							AS NewKeySignature,
		  NULL 							AS newContextID,
		  NULL 							AS NewPropertyID,
		  NULL 							AS NewKeyID, 
		  NULL 							AS NewAspect, 
		  NULL 							AS OutcomeID, 
		  NULL 							AS OutComeVID, 
		  NULL 							AS NewVarID, 
		  NULL 							AS NewVVID, 
		  0 							AS IsNewCell, 
		  0 							AS isnewPropertyDataType, 
		  0 							AS isNewKey, 
		  0 							AS IsNewTableVersion, 
		  0 							AS isNewModuleVersion, 
		  0 							AS isotherID, 
		  0 							AS isotherVVID, 
		  NULL 							AS newVVID_StartRelease, 
		  0 							AS sameAspectasPrevID, 
		  0 							AS oldVVIDEXISTSiNOTherCell, 
		  0 							AS oldIDEXISTSiNOTherCell, 
		  0 							AS sameVVIDEXISTSiNOTherCellandNewMV, 
		  0 							AS sameIDEXISTSiNOTherCellandNewMV, 
		  1 							AS NOTEXISTSameCellVVIDorhasSameNewAspect, 
		  0 							AS EXISTSActiveSameAspect, 
		  0 							AS SameNewAspectEXISTSiNOTherCellwithdiffOldVarID, 
		  0 							AS SameNewAspectEXISTSiNOTherCellwithdiffOldVarIDinNewMV, 
		  NULL 							AS ReportMsg
---  INTO 			  #cellmodelling
  FROM 			  TableVersionCell 		   tvc 
  JOIN 			  TableVersion 			   tv  ON (tvc.TableVID   = tv.TableVID) 
  JOIN 			  ModuleVersionComposition mvc ON (mvc.TableVID   = tv.TableVID) 
  JOIN 			  ModuleVersion 		   mv  ON (mvc.ModuleVID  = mv.ModuleVID) 
  LEFT OUTER JOIN VariableVersion 		   vv  ON (vv.VariableVID = tvc.VariableVID) 
  WHERE 
--  tv.TableVID=5164 and
  -- tvc.IsVoid = 0 and tvc.IsExcluded=0  AND            -- Only non-void cells will be processed
  mv.EndReleaseID IS NULL 
  -- Exclude playground Release
  and mv.StartReleaseID<>9999;


-- AND mv.StartReleaseID=@CurrentRelease
-- AND tv.ENDReleaseID IS NULL

---  ALTER TABLE #cellmodelling ALTER COLUMN NewAspect  nvarchar(100)
---  ALTER TABLE #cellmodelling ALTER COLUMN ReportMsg  nvarchar(1000) 
---  ALTER TABLE #cellmodelling ALTER COLUMN OutComeID  nvarchar(15) 
---  ALTER TABLE #cellmodelling ALTER COLUMN OutComeVID nvarchar(15) 


-- SELECT * FROM #cellmodelling order by mvstartreleaseID desc, tablecode, cellcode

-- For the Cells of the TableVersions for which it EXISTS a previous TableVersion (having ENDReleaseID=@CurrentRelease) SET vv.Old..... coordinates FROM the previous TableVersion
--

  -- DECLARE @CurrentRelease int = 5 --1020000001
  UPDATE cm
  SET    vvOldEndReleaseID	= vv.EndReleaseID,
         OldVariableID		= vv.VariableID, 
         OldVariableVID		= vv.VariableVID, 
         OldContextID		= vv.ContextID, 
         OldPropertyID		= vv.PropertyID, 
         OldKeyID			= vv.KeyID, 
         OldAspect			= (CASE 
  							     WHEN vv.keyid IS NULL THEN '' 
  							     ELSE CAST(vv.KeyID AS nvarchar) 
							   END
							  ) + '_' +
							  (CASE 
							  	 WHEN vv.PropertyID IS NULL THEN '' 
							  	 ELSE CAST(vv.PropertyID AS nvarchar) 
							   END
							  ) + '_' +
							  (CASE 
							 	 WHEN vv.ContextID IS NULL THEN '' 
							 	 ELSE CAST(vv.ContextID AS nvarchar) 
							   END
							  ) 
  FROM  #cellmodelling   cm
  JOIN  TableVersionCell tvc ON (tvc.CellID     = cm.CellID)
  JOIN  Cell 			 cl  ON (cl.CellID      = tvc.CellID) 
  JOIN  VariableVersion  vv  ON (vv.VariableVID = tvc.VariableVID)
  JOIN  TableVersion     tv  ON (tv.TableVID	= tvc.TableVID) 
  WHERE 
  -- cm.isvoid			= 0 AND   
  cm.tvstartReleaseID = @CurrentRelease  AND   
  tv.EndReleaseID     = @CurrentRelease;


-- Now for Cells existing in Aux_CellMapping table (i.e. Cells mapped from another table) set old.... Parameters those parameters of the source table 
-- because we want to express "continuity" in cell modelling and variable generation
  -- DECLARE @CurrentRelease int = 2 --1020000001
  UPDATE cm
  SET    vvOldEndReleaseID	= vv.EndReleaseID,
         OldVariableID		= vv.VariableID, 
         OldVariableVID		= vv.VariableVID, 
         OldContextID		= vv.ContextID, 
         OldPropertyID		= vv.PropertyID, 
         OldKeyID			= vv.KeyID, 
         OldAspect			= (CASE 
  							     WHEN vv.keyid IS NULL THEN '' 
  							     ELSE CAST(vv.KeyID AS nvarchar) 
							   END
							  ) + '_' +
							  (CASE 
							  	 WHEN vv.PropertyID IS NULL THEN '' 
							  	 ELSE CAST(vv.PropertyID AS nvarchar) 
							   END
							  ) + '_' +
							  (CASE 
							 	 WHEN vv.ContextID IS NULL THEN '' 
							 	 ELSE CAST(vv.ContextID AS nvarchar) 
							   END
							  ) 
  FROM  #cellmodelling   cm
  INNER JOIN Aux_CellMapping ac on ac.NewTableVID=cm.TableVID and ac.NewCellID=cm.CellID
  INNER JOIN  TableVersionCell tvc ON (tvc.CellID     = ac.OldCellID and tvc.TableVID=ac.OldTableVID)  
  INNER JOIN  Cell 			 cl  ON (cl.CellID      = tvc.CellID) 
  INNER JOIN  VariableVersion  vv  ON (vv.VariableVID = tvc.VariableVID)
  INNER JOIN  TableVersion     tv  ON (tv.TableVID	= tvc.TableVID) 
  WHERE 
  -- cm.isvoid			= 0 AND 
  cm.tvstartReleaseID = @CurrentRelease 
  
  

-- Now on those TableVersions that do not change all cell @New...@ features should be the same as the old ones.....

  UPDATE cm
  SET	 NewContextID        = OldContextID,
		 NewPropertyID		 = OldPropertyID,
		 NewKeyID			 = OldKeyID,
		 NewAspect			 = OldAspect
  FROM   #cellmodelling cm
  WHERE  cm.tvStartReleaseID != @CurrentRelease



-- isNewCell
    -- DECLARE @CurrentRelease int = 2 --1020000001 
  UPDATE #cellmodelling
  SET    isNewCell = (CASE 
                        WHEN EXISTS (SELECT tvc.* 
									 FROM   TableVersionCell tvc 
									 JOIN   TableVersion     tv2 ON  (tv2.TableVID = tvc.TableVID) 
									 WHERE  tvc.CellID       = #cellmodelling.CellID 
									 AND    tv2.Endreleaseid = @CurrentRelease 
--- SOS111 HERE WE TREAT VOID CELLS AS NEW
                                     AND    tvc.VariableVID is Not Null
									) THEN 0 
					    ELSE CASE 
						       WHEN #cellmodelling.cellid in (select ac.NewCellID from Aux_CellMapping ac where ac.NewTableVID=#cellmodelling.TableVID 
--- SOS111 HERE WE TREAT VOID CELLS AS NEW
							   AND ac.OldCellID in (select tvc2.CellID from TableVersionCell tvc2 where tvc2.TableVID=ac.OldTableVID and tvc2.VariableVID is not null)) THEN 0
							   ELSE CASE 
						          WHEN tvStartReleaseID = @CurrentRelease THEN 1 
							      ELSE 0 
							   END
						END	   
					  END
                     );

-- NewKeySignature
  UPDATE #cellmodelling
  SET    NewKeySignature = ck.[Signature]
  FROM   CompoundKey  ck 
  JOIN   TableVersion tv ON (tv.KeyID = ck.KeyID) 
  WHERE  
  -- #cellmodelling.isVoid   =  0 AND    
  #cellmodelling.TableVID =  tv.TableVID AND    
  ck.[Signature] != '';

-- NewKeyID

  UPDATE 	cm
  SET    	newKeyID = kx.KeyID 
  FROM 		#cellmodelling cm
  JOIN      CompoundKey    kx  ON (kx.[Signature] = cm.NewKeySignature)
  WHERE 	
  -- cm.isVoid = 0 AND 		
  kx.[Signature]  	 != '' AND       
  cm.tvStartReleaseID  = @CurrentRelease;

  
-- New PropertyID 

  DROP TABLE IF EXISTS #temp_property;
 
  SELECT DISTINCT
         cm.TableVID, 
		 cm.CellID, 
	    (SELECT max(p.PropertyID) 
		 FROM   Property p 
		 WHERE  p.PropertyID IN (hvc.PropertyID, 
								 hvr.PropertyID, 
								 hvs.PropertyID, 
								 tv.PropertyID
								)
		)											AS PropertyID
  INTO	 #temp_property 
  FROM			  #cellmodelling cm 
  JOIN			  Cell			 cl	 ON (cl.CellID    = cm.CellID)
  JOIN			  Tableversion	 tv	 ON (tv.Tablevid  = cm.TableVID)
  LEFT OUTER JOIN HeaderVersion  hvc ON (hvc.HeaderID = cl.ColumnID)
  LEFT OUTER JOIN HeaderVersion  hvr ON (hvr.HeaderID = cl.RowID)
  LEFT OUTER JOIN headerVersion  hvs ON (hvs.HeaderID = cl.SheetID)
  WHERE hvc.EndReleaseID IS NULL
  AND   hvr.EndReleaseID IS NULL
  AND   hvs.EndReleaseID IS NULL
  AND   cm.tvStartReleaseID = @CurrentRelease;


-- SET to #CellModelling

  UPDATE cm
  SET    newPropertyID   = tp.Propertyid 
  FROM   #cellmodelling cm
  JOIN   #temp_Property tp  ON (
								tp.CellID = cm.CellID 
							  AND 
							    tp.TableVID = cm.TableVID
							   )
  WHERE  
  -- cm.isVoid        = 0 AND 
  tvStartReleaseID = @CurrentRelease; 
  
  DROP TABLE IF EXISTS #temp_property;

  
-- New Context Signature    
-- Create table #temp_context that hosts the detailed context composition for every (TableVID, cellid) from: Row, Column, Sheet & Table ContextID
-- ATTENTION in the selection of HeaderVersions with EndRelease=Null and TableVersion with StartRelease=@CurrentRelease
  DROP TABLE IF EXISTS #temp_context;
  DROP TABLE IF EXISTS #temp_plain_context;

--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
  SELECT DISTINCT
         cm.TableVID, 
		 cm.cellid, 
		 cc.ContextID, 
		 cc.PropertyID, 
	 	 cc.ItemID,  
    	 CAST('' AS nvarchar(2000)) 	AS temp_signature
  INTO   		  #temp_context 
  FROM   		  ContextComposition cc,  
                  #cellmodelling     cm 
  INNER JOIN      cell 				 cl  ON (cl.CellID    = cm.CellID)
  INNER JOIN 	  tableversion  	 tv  ON (tv.TableVID  = cm.TableVID) 
  LEFT OUTER JOIN headerversion 	 hvc ON (hvc.HeaderID = cl.ColumnID) 
  LEFT OUTER JOIN headerversion 	 hvr ON (hvr.HeaderID = cl.RowID)
  LEFT OUTER JOIN headerversion 	 hvs ON (hvs.HeaderID = cl.SheetID)
  WHERE cm.tvStartReleaseID = @CurrentRelease
  AND   hvc.EndReleaseID IS NULL
  AND   hvr.EndReleaseID IS NULL
  AND   hvs.EndReleaseID IS NULL
  AND   cc.ContextID is not null
  AND   cc.ContextID IN (hvc.ContextID, 
		     			 hvr.ContextID,
						 hvs.ContextID,
						 tv.ContextID
							    )
	
  UPDATE tc
  SET tc.temp_signature = (   SELECT STRING_AGG((CAST(hc.PropertyID AS nvarchar) + '_' + CAST(hc.ItemID AS nvarchar)),'#') WITHIN GROUP (ORDER BY (CAST(hc.PropertyID AS nvarchar) + '_' + CAST(hc.ItemID AS nvarchar))) + '#'
                         FROM   #temp_context hc
						 WHERE  hc.CellID = tc.CellID
						 AND    hc.TableVID = tc.TableVID
					)	   
  FROM   #temp_context  tc

  SELECT DISTINCT temp_signature 
  INTO #temp_plain_context 
  FROM #temp_context

  -- SELECT * FROM #temp_context order by tablevid, cellid

-- Check for integrity the context compositions; Each PropertyID must always have One ItemID in contexts
-- select hc.tablevid, hc.cellid, hc.propertyid, count(distinct hc.itemid) as noofit, min(tv.startreleaseid) 
-- from #temp_context hc inner join tableversion tv on hc.TableVID=tv.TableVID
-- group by hc.tablevid, hc.cellid, hc.propertyid
-- having count(distinct hc.itemid)>1
-- order by hc.tablevid, hc.cellid, hc.propertyid
--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
-- NewContextID 
-- INSERT if NOT existing
  DECLARE @max_contextID int = (SELECT ISNULL(max(ContextID),1010000000) from Context WHERE ContextID>=1010000000)
  INSERT INTO Context (ContextID, [Signature], OwnerID) 
  SELECT DISTINCT @max_contextID + ROW_NUMBER() OVER(ORDER BY #temp_plain_context.[temp_Signature] ASC) AS ContextID, 
  temp_Signature, @CurrentOwnerID as OwnerID 
  FROM   #temp_plain_context
  WHERE  
  -- #cellmodelling.IsVoid = 0 AND 
  temp_Signature is not Null AND 
  trim(temp_Signature)!='' AND    
  temp_Signature NOT IN (SELECT ct2.[Signature] 
							  FROM   Context ct2
							 );
					


  INSERT INTO ContextComposition (ContextID, 
								  PropertyID, 
								  ItemID
								 )
  SELECT DISTINCT 
		 cx.ContextID, 
		 hc.PropertyID, 
		 hc.ItemID
  FROM   #temp_context hc 
  JOIN   context cx ON (cx.[Signature] = hc.temp_signature)  
  WHERE NOT EXISTS (SELECT * 
					FROM   ContextComposition cc2 
					WHERE  cc2.ContextID   = cx.ContextID 
					AND    cc2.PropertyID  = hc.PropertyID
				   );

--select * from context where signature in ('110_1510#120_1987#240_4297#249_9077#540_6317#990_6303#', 
--'110_1510#120_1987#240_4297#249_9077#540_6317#990_6303#', 
--'110_1510#120_1931#249_9077#540_4324#940_6281#', 
--'110_1510#120_1931#249_9077#540_4324#940_6281#')


-- SET NewContextID to #CellModelling

--select tc.* 
--from #temp_context tc 
--where tc.PropertyID in (select tc2.propertyid 
--from #temp_context tc2 
--where tc2.temp_signature=tc.temp_signature and tc2.PropertyID=tc.PropertyID and tc2.ItemID<>tc.ItemID)


-- Set signature for the Cell Context on #cellmodelling table from the ContextComp[osition of #temp_context
--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
  UPDATE cm
  SET    NewSignature = tc.temp_signature
  FROM   #cellmodelling cm 
  JOIN #temp_context tc on tc.CellID=cm.CellID AND tc.TableVID=cm.TableVID 
  WHERE  
  -- cm.IsVoid = 0 AND    
  cm.tvStartReleaseID = @CurrentRelease AND 
  tc.temp_signature is not NULL AND 
  tc.temp_signature<>'';

  --select * from context where signature in ('155_1180#410_3079#476_2672#', '130_4812#155_1180#365_3078#', '155_1180#476_2672#')

  --select * from #cellmodelling 

-- Set proper ContextID from Context table
  --declare @currentrelease int = 4 
  UPDATE cm
  SET    cm.newContextID = cx.contextid
  FROM   #cellmodelling cm
  JOIN   context        cx  ON (trim(cx.[Signature]) = trim(cm.NewSignature) )
  WHERE  
  -- cm.isvoid = 0 AND    
  cm.tvStartReleaseID = @CurrentRelease; 

  DROP TABLE IF EXISTS #temp_context;

  -- NewAspect = 'NewKeyID_NewPropertyID_NewContextID'

 --declare @currentrelease int = 2 
  UPDATE cm
  SET    NewAspect = (CASE 
					    WHEN newkeyid IS NULL THEN '' 
					    ELSE CAST(NewKeyID AS nvarchar) 
					  END
				     ) + '_' +
					 (CASE 
					    WHEN NewPropertyID IS NULL THEN '' 
						ELSE CAST(NewPropertyID AS nvarchar) 
					  END
					 ) + '_' +
		 			 (CASE 
					    WHEN NewContextID IS NULL THEN '' 
					    ELSE CAST(NewContextID AS nvarchar) 
					  END
					 )
  FROM  #cellmodelling cm ;
  -- WHERE cm.isvoid = 0 

  
-- SELECT * FROM #cellmodelling WHERE oldaspect <> newaspect

-- isnewPropertyDataType
-- All new cells will have isnewpropertydatatype by default
-- DECLARE @CurrentRelease int = 2   --1020000001
  UPDATE #cellmodelling
  SET    isNewPropertyDataType = 1
  WHERE  isNewCell = 1

-- For old cells we have to check the datatype of OldPropertyID & NewPropertyID

  UPDATE cm
  SET    isNewPropertyDataType = 1
  FROM   #cellmodelling cm
  WHERE NOT (
             (SELECT p1.DataTypeID 
			  FROM   Property p1 
			  WHERE  p1.PropertyID = cm.oldPropertyID
			 ) = 
			 (SELECT p2.DataTypeID 
			  FROM   Property p2 
			  WHERE  p2.PropertyID = cm.newPropertyID
			 )
			);

-- isNewKey
  UPDATE cm
  SET    isNewKey = 1
  FROM   #cellmodelling cm
  WHERE (
          cm.newKeyID IS NULL 
        AND 
		  cm.oldKeyID IS NOT NULL
		) 
  OR    (
          cm.newKeyID IS NOT NULL 
        AND 
		  cm.oldKeyID IS NULL
		) 
  OR    (cm.newKeyID != cm.oldKeyID);

-- IsNewTableVersion

  UPDATE cm
  SET    cm.isNewTableVersion = 1
  FROM   #cellmodelling cm
  WHERE  cm.tvStartReleaseID  = @CurrentRelease;

-- isNewModuleVersion
-- DECLARE @CurrentRelease int = 2  ---1020000001
UPDATE cm
  SET    cm.isNewModuleVersion = 1
  FROM   #cellmodelling cm
  WHERE  cm.mvStartReleaseID  = @CurrentRelease;

-- sameAspectAsPrevID,
  UPDATE cm
  SET    cm.sameAspectAsPrevID = 1
  FROM   #cellmodelling cm
  WHERE  cm.OldAspect = NewAspect;

-- oldVVIDExistsInOtherCell 
--  UPDATE cm
--  SET    cm.oldVVIDExistsInOTherCell = 1
--  FROM   #cellmodelling cm
--  WHERE  OldVariableVID IN (SELECT tvc.VariableVID 
--							FROM   TableVersionCell tvc 
--							WHERE  tvc.cellid != cm.cellid
--						   );

-- oldIDExistsInOtherCell, 
--  UPDATE cm
--  SET    cm.oldIDExistsInOTherCell = 1
--  FROM   #cellmodelling cm
--  WHERE  OldVariableID IN (SELECT vv.VariableID 
--						   FROM   TableVersionCell tvc 
--						   JOIN   variableversion  vv ON (tvc.variablevid=vv.variablevid)
--						   WHERE  tvc.cellid != cm.cellid
--						  );

-- sameVVIDExistsInOtherCellandNewMV, 
--  UPDATE cm
--  SET    cm.sameVVIDExistsInOtherCellandNewMV = 1
--  FROM   #cellmodelling cm
--  WHERE  OldVariableVID IN (SELECT cm2.OldVariableVID 
--							FROM   #cellmodelling cm2 
--							WHERE  cm2.cellid		   != cm.cellid 
--							AND    cm.mvStartReleaseID  = @CurrentRelease 
--							AND    cm2.mvStartReleaseID = @CurrentRelease
--						   );

-- sameIDExistsInOtherCellandNewMV, 
--  UPDATE cm
--  SET    cm.sameIDExistsInOtherCellandNewMV = 1
--  FROM   #cellmodelling cm
--  WHERE  OldVariableID IN (SELECT cm2.OldVariableID 
--						   FROM   #cellmodelling cm2 
--						   WHERE  cm2.cellid					 != cm.cellid 
--						   AND 	  cm.mvStartReleaseID = @CurrentRelease 
--						   AND    cm2.mvStartReleaseID            = @CurrentRelease
--						  );


-- NotExistSameCellVVIDorHasSameNewAspect, 
--  UPDATE cm
--  SET    NotExistSameCellVVIDorHasSameNewAspect = 0
--  FROM	 #cellmodelling cm
--  WHERE  OldVariableVID IN (SELECT vv.VariableVID 
--						    FROM   TableVersionCell tvc 
--						    JOIN   VariableVersion  vv  ON (tvc.VariableVID = vv.VariableVID) 
--						    WHERE  tvc.CellID      != cm.CellID  
--						    AND    vv.EndReleaseID IS NULL 
--						    AND NOT (
--									 (
--									  cm.newKeyID IS NULL 
--								     OR 
--									  cm.newKeyID = vv.KeyID
--									 ) 
--								   AND 
--									 (
--									  cm.newContextID IS NULL 
--								     OR 
--									  cm.newContextID = vv.ContextID
--									 ) 
--								   AND cm.newPropertyID = vv.PropertyID
--								    ) 
--						   );
  
   
-- ExistsActiveSameAspect, 
--  UPDATE cm
--  SET    ExistsActiveSameAspect = 1
--  FROM   #cellmodelling cm
--  WHERE  
--  cm.NewAspect is not Null 
--  AND cm.NewAspect in (SELECT cm2.NewAspect from #cellmodelling cm2 where cm2.CellID<>cm.CellID and cm2.vvOldEndReleaseID is null);

-- SameNewAspectExistsInOtherCellWithDiffOldVarID, 
--  UPDATE cm
--  SET    SameNewAspectExistsInOtherCellWithDiffOldVarID = 1
--  FROM   #cellmodelling cm
--  WHERE  cm.NewAspect IN (SELECT cm2.NewAspect 
--  					      FROM   #cellmodelling cm2 
--  					      WHERE  cm2.CellID        != cm.CellID 
--  					      AND    cm2.OldVariableID != cm.OldVariableID
--  					     ) 
--  	    
-- OR  EXISTS (SELECT vv.VariableID 
--			  FROM   TableVersionCell tvc 
--			  JOIN   VariableVersion  vv  ON tvc.VariableVID = vv.VariableVID 
--			  WHERE  tvc.CellID      != cm.CellID  
--			  AND    vv.EndReleaseID IS NULL 
--			  AND    vv.VariableID   != cm.OldVariableID 
--			  AND   (  
--			         (
--					  cm.newKeyID IS NULL 
--					 OR 
--					  cm.newKeyID = vv.KeyID
--					 ) 
--				   AND 
--				     (
--					  cm.newContextID IS NULL 
--					 OR 
--					  cm.newContextID = vv.ContextID
--					 ) 
--				   AND cm.newPropertyID = vv.PropertyID
--				    ) 
--			 );

-- SameNewAspectExistsInOtherCellWithDiffOldVarIDinNewMV 
--  UPDATE cm
--  SET    SameNewAspectExistsInOtherCellWithDiffOldVarIDInNewMV = 1
--  FROM   #cellmodelling cm
--  WHERE  NewAspect IN (SELECT cm2.NewAspect 
--  					   FROM   #cellmodelling cm2 
--  					   WHERE  cm2.CellID 			!= cm.CellID 
--  					   AND    cm2.OldVariableID 	!= cm.OldVariableID  
--  					   AND    cm.mvStartReleaseID	 = @CurrentRelease 
--  					   AND    cm2.mvStartReleaseID   = @CurrentRelease
--  				      );

-- You can test Flags in #CellModelling if you want
-- select * from #cellmodelling where SameNewAspectExistsinotherCellwithdiffOldVarID=1

--0 as IsNewCell, 
--0 as isnewPropertyDataType, 
--0 as isNewKey, 
--0 as IsNewTableVersion, 
--0 as isNewModuleVersion, 
--0 as isotherID, 
--0 as isotherVVID, 
--null as newVVID_StartRelease, 
--0 as sameAspectasPrevID, 
--0 as oldVVIDExistsinOtherCell, 
--0 as oldIDExistsinOtherCell, 
--0 as sameVVIDexistsinOtherCellandNewMV, 
--0 as sameIDexistsinOtherCellandNewMV, 
--1 as NotExistSameCellVarOrElseSameNewAspect, 
--1 as NotExistSameCellVVIDorhasSameNewAspect, 
--0 as existsActiveSameAspect, 
--0 as SameNewAspectExistsinotherCellwithdiffOldVarID, 
--0 as SameNewAspectExistsinotherCellwithdiffOldVarIDinNewMV, 


-- VII.	Tool THEN checks the existence of the errors described below for all the table versions  in this release (in moduleVerison with StartRelease = currentRelease) :
-- 1.	If there exists old cells with VVID EndRelease != null: Report error, there are expired variable versions in cells,  modelling must be Updated for them 
--      AND necessarily new TableVersion has to be created (if TableVersIon.StartRelease < CurrentRelease).
 --declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
 INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID)
 
  SELECT DISTINCT 
  '5_1' as ViolationCode, 
  'Error 1: Expired VariableVersion in active TableVersion' as Violation,
  1 as isBlocking,
  cm.TableVID as TableVID, 
  Null as OldTableVID,
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID
  FROM   #CellModelling cm 
  JOIN   TableVersion   tv ON (tv.TableVID = cm.TableVID)
  WHERE  cm.mvStartReleaseID = @CurrentRelease 
  AND    tv.StartReleaseID  != @CurrentRelease 
  AND    cm.vvOldEndReleaseID IS NOT NULL 
  AND	 cm.IsVoid=0;

-- checking cells with active same variablevid
-- SELECT tvc.*, tv.StartReleaseID, tv.ENDReleaseID, vv.ENDreleaseid AS varENDrelease  
-- FROM tableversioncell tvc INNER JOIN tableversion tv ON tvc.tablevid=tv.tablevid INNER JOIN variableversion vv ON tvc.VariableVID=vv.VariableVID
-- WHERE -
-- tvc.variablevid in (SELECT oldvariablevid FROM #cellmodelling WHERE EXISTSActiveSameAspect=1 AND mvstartreleaseid=2) 
-- order by tvc.variablevid, tv.code

--  SELECT * 
--  FROM   tableversioncell tvc 
--  WHERE  tvc.variablevid = 446178;
--
-- 2.	 If there EXISTS 2 or more cells having the same vvid in previous tableversion 
--       but now they have different aspects in table version of curent modules, 
--       AND those cells have no changes ON main property data type AND ON table key: 
--       report error, it is NOT possible to have two versions of same variable in the same release 
--       (list the cells using these two variable versions) 
--
--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID, Cell2ID, Cell2Code)
  SELECT DISTINCT 
  '5_2' as ViolationCode, 
  'Error 2: These 2 Cells had same old VariableID but now they have different aspect' AS Violation,
  1 as isBlocking,
  cm.TableVID as TableVID, 
  tv.Code as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID, 
  cm2.CellID AS Cell2ID, 
  cm2.CellCode AS Cell2Code
  FROM   #CellModelling  cm 
  JOIN   TableVersion    tv  ON (tv.TableVID        = cm.TableVID) 
  JOIN   #cellmodelling  cm2 ON (cm2.OldVariableID = cm.OldVariableID) 
  WHERE  cm.IsNewCell  = 0 
  AND    cm2.IsNewCell = 0 
  AND    cm2.CellID    > cm.CellID 
  AND    cm.NewAspect != cm2.NewAspect 
  AND    (
          (
  		   cm.OldKeyID IS NULL 
  	     AND 
  	       cm.NewKeyID IS NULL
  		  ) 
  		OR 
  		   cm.NewKeyID = cm.OldKeyID
  	     ) 
  AND    (
          (
  		   cm2.OldKeyID IS NULL 
  	     AND 
  	       cm2.NewKeyID IS NULL
  		  ) 
  		OR 
  		   cm2.NewKeyID=cm2.OldKeyID
  	     )
  AND    cm.isNewPropertyDataType  = 0 
  AND    cm.mvStartReleaseID	   = @CurrentRelease
  AND    cm2.isNewPropertyDataType = 0 
  AND    cm2.mvStartReleaseID	   = @CurrentRelease 
  AND	 cm.IsVoid=0
  ORDER BY cm.TableVID, 
           cm.CellCode;
  
-- Test again this rule based ON existing flags
-- SELECT * FROM #cellmodelling WHERE NOTEXISTSameCellVVIDorhasSameNewAspect=0 AND isNewKey=0 AND isnewPropertyDataType=0

-- 3.	If there exist cells with different old variableIDs but have the same new Aspects in the table version of current module:  
--      report error, it is NOT possible to have two different VariableIDs whose VariableVIDs are Starting in CurrentRelease 
--      AND have the same New Aspects.
--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID, Cell2ID, Cell2Code, NewAspect)
  SELECT DISTINCT 
  '5_3' as ViolationCode, 
  'Error 3: These 2 Cells had different old VariableVID but now they have SAME aspect' AS Violation,
  1 as isBlocking,
  cm.TableVID as TableVID, 
  tv.Code as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID, 
  cm2.CellID AS Cell2ID, 
  cm2.CellCode AS Cell2Code, 
  cm.newAspect as NewAspect
  FROM   #CellModelling cm 
  JOIN   TableVersion   tv  ON (tv.TableVID   = cm.TableVID) 
  JOIN   #cellmodelling cm2 ON (cm2.NewAspect = cm.NewAspect) 
  WHERE  cm.IsNewCell  	      = 0 
  AND    cm2.IsNewCell 	      = 0 
  AND    cm2.CellID           > cm.CellID 
  AND    cm.OldVariableID    != cm2.OldVariableID 
  AND    cm.mvStartReleaseID  = @CurrentRelease
  AND    cm2.mvStartReleaseID = @CurrentRelease 
  AND	 cm.IsVoid=0
  ORDER BY cm.TableVID, 
		   cm.CellCode;

-- 4.	If there exists a VOID CELL that has the same aspect as another non-Voic Cell then the first Cell is not really Void and this is an ERROR
-- DECLARE @CurrentRelease int = 2 --1020000001 
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, Cell2ID, Cell2Code, NewAspect)
  SELECT DISTINCT 
  '5_4' as ViolationCode, 
  'Error 4: The First Cell is Void and the Second Cell has the same New Aspect but is non-void' AS Violation,
  1 as isBlocking,
  cm.TableVID as TableVID, 
  tv.Code as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm2.CellID AS Cell2ID, 
  cm2.CellCode AS Cell2Code, 
  cm.newAspect as NewAspect
  FROM   #CellModelling   cm 
  JOIN   TableVersion     tv  ON (tv.TableVID   = cm.TableVID) 
  JOIN   TableVersionCell tvc ON (tvc.TableVID   = cm.TableVID and tvc.CellID=cm.CellID) 
  JOIN   #cellmodelling   cm2 ON (cm2.NewAspect = cm.NewAspect) 
  WHERE  tvc.IsVoid  	      = 1 
  AND    cm2.isVoid 	      = 0 
  AND    cm2.CellID           <> cm.CellID 
  AND    tv.StartReleaseID=@CurrentRelease
  ORDER BY cm.TableVID, 
		   cm.CellCode;


  --declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; 
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, Cell2ID, Cell2Code, NewAspect)
  SELECT DISTINCT 
  '5_4' as ViolationCode, 
  'Error 4: The First Cell is Void and the Second Cell has the same New Aspect but is non-void' AS Violation,
  1 as isBlocking,
  cm.TableVID as TableVID, 
  tv.Code as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm2.CellID AS Cell2ID, 
  cm2.CellCode AS Cell2Code, 
  cm.newAspect as NewAspect
  FROM   #CellModelling   cm 
  JOIN   TableVersion     tv  ON (tv.TableVID   = cm.TableVID) 
  JOIN   TableVersionCell tvc ON (tvc.TableVID   = cm.TableVID and tvc.CellID=cm.CellID) 
  JOIN   #cellmodelling   cm2 ON (cm2.NewAspect = cm.NewAspect) 
  WHERE  tvc.IsVoid  	      = 1 
  AND    cm2.isVoid 	      = 0 
  AND    cm2.CellID           <> cm.CellID 
  AND    cm2.tvStartReleaseID=@CurrentRelease
  ORDER BY cm.TableVID, 
		   cm.CellCode;


-- VIII.	If any of the above errors exist THEN: STOP Variable Generation AND review the Modelling of the corresponding TableVersion(s).
-- NOTe for awareness of Modellers AND other Stakeholders:
-- To amEND these errors, there are the following alternatives (always by establishing new TableVersion):
-- •	UPDATE modelling ON some of the cells’ Header(s) (if the modellers really want this)
-- or
-- •	Create New Headers AND maintain existing Modelling. In this CASE, new Cells will be created AND Variable Generation can normally proceed ON New Cells. Old cells are NOT related to new cells in any way.

-- If there are No errors that would stop Variable Generation AS dictated above, the tool starts the Variable Generation for the cells of All TableVersions with StartRelease = Current Release .

IF 1 in (SELECT isBlocking FROM ModelViolations) 
  PRINT 'Errors in Cell Modelling Found: Variable Generation cannot Proceed'

ELSE

BEGIN

--declare @currentrelease int = 1010000009; declare @currentownerid int = 1012; declare @maxContextID int; declare @maxKeyID int; declare @maxItemID int; declare @maxVariableID int; declare @maxVariableVID int;  
--MAIN PROCESS OF FACT VARIABLE GENERATIon
-- 1.	Find all the old cells having the old Aspect = new Aspect AND assign VVID using the VVID in previous table version
  UPDATE cm
  SET    cm.newVarID   = cm.OldVariableID,
		 cm.newVVID    = cm.OldVariableVID,
		 cm.OutcomeID  = 'OLD',
		 cm.OutcomeVID = 'OLD',
         cm.ReportMsg  = CASE 
						   WHEN cm.mvStartReleaseID != @CurrentRelease THEN 'OLD ModuleVersion: ' 
						   ELSE 
						     CASE 
						       WHEN cm.tvStartReleaseID != @CurrentRelease THEN 'NEW ModuleVersion & OLD TableVersion ' 
						       ELSE 'Old Cell with the Same Aspect: Old VariableID & Old VariableVID' 
						     END   
					     END 
  FROM   #cellmodelling cm
  WHERE  
  cm.isVoid = 0 AND 
  cm.OldAspect = cm.NewAspect AND 
  (cm.vvOldEndReleaseID is NULL OR cm.TvStartReleaseID!=@CurrentRelease);
  

-- 1b.	new Aspect!=oldAspect but NewAspect exists in a VVID of the samevarID with VV.EndReleaseID=null.
  UPDATE cm
  SET    cm.newVarID   = cm.OldVariableID,
		 cm.newVVID    = cm2.NewVVID,
		 cm.OutcomeID  = 'OLD',
		 cm.OutcomeVID = 'OLD',
         cm.ReportMsg  = CASE 
						   WHEN cm.mvStartReleaseID != @CurrentRelease THEN 'OLD ModuleVersion: ' 
						   ELSE 
						     CASE 
						       WHEN cm.tvStartReleaseID != @CurrentRelease THEN 'NEW ModuleVersion & OLD TableVersion ' 
						       ELSE 'Old Cell with the Differnet Aspect but Existing active VariableVID for the same Old VariableID' 
						     END   
					     END 
  FROM   #cellmodelling cm
  JOIN   #cellmodelling cm2 ON cm2.NewVarID=cm.OldVariableID AND cm2.NewAspect=cm.NewAspect 
  JOIN   VariableVersion vv2 ON vv2.VariableVID=cm2.NewVVID 
  WHERE  
  cm2.CellID<>cm.CellID AND 
  cm.NewVVID is NULL AND 
  cm2.NewVVID is NOT NULL AND 
  cm2.IsVoid = 0 AND 
  cm.isVoid = 0 AND 
  cm.OldAspect <> cm.NewAspect AND 
  cm.TvStartReleaseID=@CurrentRelease AND 
  vv2.EndReleaseID is NULL ;

  
  -- SELECT * FROM #cellmodelling WHERE oldaspect<>NewAspect

-- 2.	Group Cells by Aspect: For each group of cells with the same (new) Aspect, create 2 sub-lists:
-- a.	List of old cells WHERE oldKey=New Key AND Data Type of Old PropertyID = Data Type of New PropertyID (such Cells are considered of having less significant change that should NOT necessarily lead to new VariableID but ONly to New VariableVID)
-- b.	Other cells.

-- The steps to follow to generate variables for these cells are based ON the principle that all cells with same aspect will be assigned same VariableID  AND same VariableVID, AS follows:
-- 2.1.	If there exist any cells in list (a) THEN all the cells in this list should refer to the same old VariableID for the same Aspect 
--       (otherwise we would have error (3) AS dictated above),
--       • If these cells have no VVID (means NOT associated to a variable in the first step): 

 
  DROP TABLE IF EXISTS #new_Aspects 

---  CREATE TABLE #new_Aspects (newAspect nvarchar(100), newKeyID int, newPropertyID int, newContextID int, AspectID int)

  SELECT DISTINCT 
         cm.NewAspect, 
		 cm.NewKeyID, 
		 cm.NewPropertyID, 
		 cm.newContextID,
		 CAST(NULL AS int) AspectID
  INTO   #new_Aspects
  FROM   #cellmodelling cm
  WHERE  cm.NewVVID          IS NULL 
  AND    cm.NewPropertyID    IS NOT NULL 
  AND	 cm.isVoid			 = 0
  AND    cm.tvStartReleaseID = @CurrentRelease


-- Create a new VariableVID (AND maintain Old VariableID for this new created VariableVID) AND assign this VVID to these cells.
-- Attention! We only include Cells with NewKeyID=oldKeyID AND NOT isNewPropertyDataType
  SET @maxVariableVID = (SELECT ISNULL(max(VariableVID),1010000000) from VariableVersion WHERE VariableVID>=1010000000)
  INSERT INTO VariableVersion (VariableVID, 
							   VariableID, 
  							   PropertyID, 
  							   ContextID, 
  							   KeyID, 
  							   StartReleaseID, 
  							   ENDReleaseID
  							  )
  SELECT DISTINCT 
         @maxvariableVID + ROW_NUMBER() OVER(ORDER BY na.NewAspect ASC) AS ContextID, 
  	     cm.OldVariableID, 
  	     na.newPropertyID, 
  	     na.newContextID, 
  	     na.newKeyID, 
  	     @CurrentRelease 	AS sr, 
  	     null 				AS er
  FROM   #new_Aspects   na 
  JOIN   #cellmodelling cm ON (na.newAspect = cm.newAspect) 
  WHERE  cm.IsNewCell			  = 0 
  AND    ISNULL(cm.NewKeyID, -1)  = ISNULL(cm.OldKeyID, -1)
  AND    cm.isNewPropertyDataType = 0 
  AND    cm.NewVVID is null
  AND	 cm.isVoid				  = 0	
  AND cm.OldVariableID is not NULL
  AND NOT EXISTS (SELECT * FROM VariableVersion vv2 WHERE vv2.VariableID=cm.oldVariableID AND vv2.StartReleaseID=@CurrentRelease) 


-- ATTENTION: As long as we inserted new VariableVersions, then for the corresponding VariableIDs we have to set EndRelease=CurrentRelease in the previous versions 
-- (those with SR<>CurrentRelease & ER=Null)
-- DECLARE @CurrentRelease int = 2    --1020000001
  UPDATE vv
  SET    EndReleaseID = @CurrentRelease 
  FROM   #New_Aspects na 
  JOIN   #cellmodelling cm  ON (na.NewAspect  = cm.NewAspect) 
  JOIN   VariableVersion vv ON (vv.VariableID = cm.oldVariableID)
  WHERE  cm.IsNewCell=0 
  AND    ISNULL(cm.NewKeyID, -1) = ISNULL(cm.OldKeyID, -1)
  AND	 cm.isVoid				  = 0	
  AND	 cm.isnewPropertyDataType  = 0  
  AND    vv.StartReleaseID		  != @CurrentRelease 
  AND    vv.EndReleaseID		  IS NULL
  AND    EXISTS (SELECT * 
                 FROM VariableVersion vv2 
				 WHERE vv2.StartReleaseID=@CurrentRelease 
				 AND vv2.EndReleaseID is Null
				 AND vv2.VariableID=vv.VariableID
                )



-- DECLARE @CurrentRelease int = 2     ---1020000001
  UPDATE cm
  SET    cm.newVarID   = cm.oldVariableID,
		 cm.NewVVID    = vv.VariableVID,
		 cm.OutcomeID  ='OLD',
		 cm.OutcomeVID ='NEW', 
		 cm.ReportMsg  = 'Old Cell with Different Aspect but same Key & same data type for Main Property: Old VariableID & New VariableVID. '
  FROM   #cellmodelling  cm
  JOIN   VariableVersion vv ON (
								vv.VariableID = cm.oldVariableID 
							  AND 
							    vv.PropertyID = cm.newPropertyID
							   )
  WHERE  cm.tvStartReleaseID		  = @CurrentRelease 
  AND 	 cm.IsNewCell				  = 0 
  AND 	 cm.NewVVID					  IS NULL 
  AND 	 vv.ENDReleaseID			  IS NULL
  AND 	 vv.StartReleaseID			  = @CurrentRelease 
  AND    ISNULL(cm.newKeyID, -1)      = ISNULL(vv.KeyID, -1)
  AND    ISNULL(cm.newContextid, -1)  = ISNULL(vv.ContextID, -1)
  AND    cm.isVoid = 0


-- a. if OldAspect=NewAspect but NewVVID (and same VarID) and OldVVID.EndRelease!=Null then 
-- WARNING that the same Aspect is re-employed by the same VarID that in the meantime was associated with a different aspect.
  UPDATE cm
  SET    cm.ReportMsg  = 'Old VariableID & New VariableVID. WARNING: Old Cell with Same Aspect but old_vv_EndREelease_not_Null. Its VarID may have been employed by Other VVID in the meantime different than original VVID.'
  FROM   #cellmodelling  cm
  WHERE  cm.tvStartReleaseID		  = @CurrentRelease 
  AND    cm.OldAspect = cm.NewAspect
  AND 	 cm.IsNewCell				  = 0 
  AND	 cm.OutcomeID  ='OLD'
  AND	 cm.OutcomeVID ='NEW' 
  AND 	 cm.NewVVID	IS NOT NULL 
  AND    cm.vvOldEndReleaseID is Not Null 
  AND    cm.isVoid = 0


  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID)
  SELECT DISTINCT 
  '5_5' as ViolationCode, 
  'WARNING: Old Cell with Same Aspect but old_vv_EndREelease_not_Null. Its VarID may have been employed by Other VVID in the meantime different than original VVID.' AS Violation,
  0 as isBlocking,
  cm.TableVID as TableVID, 
  cm.TableCode as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID 
  FROM   #cellmodelling  cm
  WHERE  cm.tvStartReleaseID		  = @CurrentRelease 
  AND    cm.OldAspect = cm.NewAspect
  AND 	 cm.IsNewCell				  = 0 
  AND	 cm.OutcomeID  ='OLD'
  AND	 cm.OutcomeVID ='NEW' 
  AND 	 cm.NewVVID	IS NOT NULL 
  AND    cm.vvOldEndReleaseID is Not Null 
  AND    cm.isVoid = 0


  
-- b.	IF there exists an old active VariableVersion (of another VariableID) in the DB (with EndRelease=Null) whose Aspect=Cell.Aspect, then in the generation report record: 
--     “: the cells in the modules xx  have the same aspects as the cell in the current module yy but they have different variables.”
  UPDATE cm 
  SET    cm.ReportMsg = cm.ReportMsg + 'The cell '+ tvc.CellCode + ', in the module '+ mv.Code + ' have the same aspects AS the cell in the current module '+ cm.ModuleCode + ' but they have different variables.'
  FROM   #cellmodelling				cm
  JOIN   [VariableVersion] 			vv  ON (vv.PropertyID  = cm.newPropertyID)
  JOIN   [TableVersionCell] 		tvc ON (vv.VariableVID = tvc.VariableVID) 
  JOIN   [ModuleVersionComposition] mvc ON (mvc.TableVID   = tvc.TableVID) 
  JOIN   [ModuleVersion]      		mv  ON (mv.ModuleVID   = mvc.ModuleVID) 
  WHERE  cm.tvStartReleaseID		  = @CurrentRelease
  AND 	 tvc.CellID					 != cm.cellid 
  AND 	 cm.NewVVID					  IS NOT NULL 
  AND    ISNULL(cm.newKeyID, -1)      = ISNULL(vv.KeyID, -1)
  AND    ISNULL(cm.newContextID, -1)  = ISNULL(vv.ContextID, -1)
  AND    cm.NewVarID					 != vv.VariableID 
  AND	 cm.isVoid				  = 0	
  AND    mv.EndReleaseID = Null 


-- First if is same aspect as another cell from a non-changing module, keep the rule as Warning
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID)
  SELECT DISTINCT 
  '5_6' as ViolationCode, 
  'The cell '+ tvc.CellCode + ', in the module '+ mv.Code + ' have the same aspects AS the cell '+ cm.CellCode+' of the current module '+ cm.ModuleCode + ' but they have different variables.' AS Violation,
  0 as isBlocking,
  cm.TableVID as TableVID, 
  cm.TableCode as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID 
  FROM   #cellmodelling				cm
  JOIN   [VariableVersion] 			vv  ON (vv.PropertyID  = cm.newPropertyID)
  JOIN   [TableVersionCell] 		tvc ON (vv.VariableVID = tvc.VariableVID) 
  JOIN   [ModuleVersionComposition] mvc ON (mvc.TableVID   = tvc.TableVID) 
  JOIN   [ModuleVersion]      		mv  ON (mv.ModuleVID   = mvc.ModuleVID) 
  WHERE  cm.mvStartReleaseID		  = @CurrentRelease
  AND 	 tvc.CellID					 != cm.cellid 
  AND 	 cm.NewVVID					  IS NOT NULL 
  AND    ISNULL(cm.newKeyID, -1)      = ISNULL(vv.KeyID, -1)
  AND    ISNULL(cm.newContextID, -1)  = ISNULL(vv.ContextID, -1)
  AND    cm.NewVarID					 != vv.VariableID 
  AND	 cm.isVoid				  = 0	
  AND	 mv.EndReleaseID is NULL
  AND	 mv.StartReleaseID!=@CurrentRelease 


-- Secpnd;y if is same aspect as another cell from a changing module in current release, make the rule blocking 
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID)
  SELECT DISTINCT 
  '5_6' as ViolationCode, 
  'The cell '+ tvc.CellCode + ', in the module '+ mv.Code + ' have the same aspects AS the cell '+ cm.CellCode+' of the current module '+ cm.ModuleCode + ' but they have different variables.' AS Violation,
  1 as isBlocking,
  cm.TableVID as TableVID, 
  cm.TableCode as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID 
  FROM   #cellmodelling				cm
  JOIN   [VariableVersion] 			vv  ON (vv.PropertyID  = cm.newPropertyID)
  JOIN   [TableVersionCell] 		tvc ON (vv.VariableVID = tvc.VariableVID) 
  JOIN   [ModuleVersionComposition] mvc ON (mvc.TableVID   = tvc.TableVID) 
  JOIN   [ModuleVersion]      		mv  ON (mv.ModuleVID   = mvc.ModuleVID) 
  WHERE  cm.mvStartReleaseID		  = @CurrentRelease
  AND 	 tvc.CellID					 != cm.cellid 
  AND 	 cm.NewVVID					  IS NOT NULL 
  AND    ISNULL(cm.newKeyID, -1)      = ISNULL(vv.KeyID, -1)
  AND    ISNULL(cm.newContextID, -1)  = ISNULL(vv.ContextID, -1)
  AND    cm.NewVarID					 != vv.VariableID 
  AND	 cm.isVoid				  = 0	
  AND	 mv.EndReleaseID is NULL
  AND	 mv.StartReleaseID = @CurrentRelease 



-- c. If there exist other cells  in modules not being  updated in the release,  but having the same variable, then in the generation report, 
-- record: "Cell has new variable version, but other cells in modules such as x, y having the same variable not being updated in this release"
  UPDATE cm
  SET    cm.ReportMsg  = 'Cell has new variable version, but other cells in modules such as: ' + 
  (select min(cm3.ModuleCode) from #cellmodelling cm3 
							  where cm3.oldVariableID=cm.oldVariableID and cm3.mvStartReleaseID<>@CurrentRelease AND cm3.vvOldEndReleaseID is not null) + 
  ', have the same variableID with old VariableVID not being updated in this release'
  FROM   #cellmodelling  cm
  WHERE  cm.tvStartReleaseID		  = @CurrentRelease 
  AND 	 cm.IsNewCell				  = 0 
  AND	 cm.OutcomeID  ='OLD'
  AND	 cm.OutcomeVID ='NEW' 
  AND 	 cm.NewVVID	IS NOT NULL 
  AND    cm.isVoid = 0
  AND    cm.oldVariableID in (select cm2.oldVariableID from #cellmodelling cm2 
							  where cm2.mvStartReleaseID<>@CurrentRelease AND cm2.vvOldEndReleaseID is not null)


  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode, VVEndReleaseID)
  SELECT DISTINCT 
  '5_6' as ViolationCode, 
'Cell has new variable version, but other cells in modules such as: ' + 
  (select min(cm3.ModuleCode) from #cellmodelling cm3 
							  where cm3.oldVariableID=cm.oldVariableID and cm3.mvStartReleaseID<>@CurrentRelease AND cm3.vvOldEndReleaseID is not null) + 
  ', have the same variableID with old VariableVID not being updated in this release' AS Violation,
  0 as isBlocking,
  cm.TableVID as TableVID, 
  cm.TableCode as TableCode, 
  cm.CellID as CellID, 
  cm.CellCode  as CellCode, 
  cm.vvOldEndReleaseID as VVEndReleaseID 
  FROM   #cellmodelling  cm
  WHERE  cm.tvStartReleaseID		  = @CurrentRelease 
  AND 	 cm.IsNewCell				  = 0 
  AND	 cm.OutcomeID  ='OLD'
  AND	 cm.OutcomeVID ='NEW' 
  AND 	 cm.NewVVID	IS NOT NULL 
  AND    cm.isVoid = 0
  AND    cm.oldVariableID in (select cm2.oldVariableID from #cellmodelling cm2 
							  where cm2.mvStartReleaseID<>@CurrentRelease AND cm2.vvOldEndReleaseID is not null)




-- 2.	If there exist cells in list (b) THEN (in this CASE we canNOT maintain old VariableID of the same Cell if this ever EXISTS):  
-- •	IF there EXISTS an active VariableVersion (created in the previous step or exist in DB with ENDRelease = null) whose Aspect=Cell.Aspect, 
-- THEN assign the latest VVID (most recent startRelease) to all the Cells with this Aspect in list (b). 
-- 
-- DECLARE @CurrentRelease int = 2   ---1020000001
  UPDATE cm
  SET    newVarID   = vv.VariableID,
		 NewVVID    = vv.VariableVID,
		 OutcomeID  = 'OTHER ' + (SELECT CASE 
										   WHEN EXISTS 
										   (SELECT * 
										   FROM VariableVersion vv2 
										   WHERE 
										   vv2.StartReleaseID <> @CurrentRelease 
										   AND vv2.VariableID=vv.VariableID
										   ) THEN 'OLD' 
										   ELSE 'NEW' 
										 END
								 ),
		 OutcomeVID = 'OTHER ' + (SELECT CASE 
										   WHEN vv.StartReleaseID = @CurrentRelease THEN 'NEW' 
										   ELSE 'OLD' 
										 END
								 ), 
  -- a.	IF it is an Old Cell: 
  -- i.	IF the assigned VariableID is an old variable; THEN record in the generation report an old cell (changing Main property or keys) has aNOTher variable (already used in other cells)
  -- ii.ELSE ( new variable N/A yet here), THEN THEN record in the generation report an old cell (changing Main property of keys) has a new created variable 
  -- b.	ELSE (new cell)
  -- i.	IF the variable is an old variable; THEN record in the generation report  a new cell has a aNOTher variable (already used in other cells) 
         ReportMsg = CASE 
		               WHEN IsNewCell = 0 THEN 'An old cell (changing Main property or keys) has another variable (already used in other cells)' 
					   ELSE 'A new cell has a another variable (already used in other cells)' 
					 END
  FROM   #cellmodelling      cm 
  JOIN   [VariableVersion]   vv ON (
							  	    ISNULL(vv.KeyID, -1)      = ISNULL(cm.newKeyID, -1) 
							  	  AND 
							  	    ISNULL(vv.ContextID, -1)  = ISNULL(cm.newContextID, -1) 
							      AND 
							  	    vv.PropertyID = cm.newPropertyID
								  )
-- Here we only deal with Fact Variables; hence we need to update this
  JOIN	[Variable]			 v	ON (v.VariableID = vv.VariableID AND v.Type = 'fact' )
  JOIN Release rl on (rl.ReleaseID=vv.StartReleaseID)
  WHERE  cm.tvStartReleaseID = @CurrentRelease
  AND    cm.NewVVID			 IS NULL 
  AND    vv.EndReleaseID	 IS NULL

  -- Note: If more than one different VariableVersions (From different VariableIDs) exist with this same Aspect, then assign to the current cells, 
--       the VariableVID (AND corresponding VariableID) with max(StartReleaseID).
--
  AND    rl.[Date] IN (SELECT MAX(rl2.[Date]) 
				       FROM   VariableVersion  vv2  
					   JOIN   Release          rl2 ON rl2.ReleaseID = vv2.StartReleaseID 
					   WHERE  vv2.EndReleaseID IS NULL 
					   AND    ISNULL(vv2.keyid,      -1) = ISNULL(cm.newkeyid,      -1)
					   AND    ISNULL(vv2.contextid,  -1) = ISNULL(cm.newcontextid,  -1)
					   AND    vv2.propertyid = cm.newpropertyid
					  )
  AND    cm.isVoid = 0
-- select * from #cellmodelling where newaspect in (select newaspect from #cellmodelling where cellcode like '{C_03.00, r0330, %')

-- DECLARE @CurrentRelease int = 1020000001
-- (now delete all the entries FROM new aspect that have already been assigned a VariableVID or all the nEWaSPECTS CORRESPONDING TO VOID CELLS) 
  DELETE na 
  FROM   #new_Aspects   na 
  WHERE  not exists 
			(select * 
			from #cellmodelling cm 
			where cm.newAspect=na.newAspect and 
			cm.newVVID is null and 
			cm.IsVoid=0 and 
			cm.TvStartReleaseID=@CurrentRelease)


  DROP TABLE IF EXISTS #InsertVarID;
  -- SET IDENTITY_INSERT [Variable] ON

  SELECT ((SELECT ISNULL(MAX(VariableVID),1010000000) FROM [VariableVersion] WHERE VariableVID>=1010000000) + ROW_NUMBER() OVER (ORDER BY NewPropertyID)) as VariableID,
		          'fact' as [Type],
				  NewPropertyID as PropertyID,
				  NewContextID as ContextID,
				  NewKeyID as KeyID, 
				  NewAspect
          INTO #InsertVarID 
		  FROM #new_Aspects;

    INSERT INTO Variable (VariableID, [Type], OwnerID) 
	SELECT VariableID, [Type], @CurrentOwnerID  
	FROM #InsertVarID
    WHERE VariableID not in (SELECT v2.VariableID FROM Variable v2)
    
	-- SET IDENTITY_INSERT [Variable] OFF;
 
     

  -- SET IDENTITY_INSERT [VariableVersion] ON;
  INSERT INTO VariableVersion (VariableVID,
							   VariableID, 
							   PropertyID, 
							   ContextID, 
							   KeyID, 
							   StartReleaseID, 
							   EndReleaseID
							  )
   SELECT DISTINCT 
         iv.VariableID			AS VariableVID,
		 iv.VariableID  		AS VariableID, 
		 na.NewPropertyID, 
		 na.NewContextID, 
		 na.NewKeyID, 
		 @CurrentRelease 		AS sr, 
		 NULL 			 		AS er
  FROM   #new_Aspects na
  JOIN   #InsertVarID   iv ON (
							 iv.PropertyID = na.newPropertyID 
                           AND 
						     isnull(iv.ContextID,-1)  = isnull(na.newContextID,-1) 
						   AND 
						     isnull(iv.KeyID,-1)  = isnull(na.newKeyID,-1) 
							);
  -- SET IDENTITY_INSERT [VariableVersion] OFF;

  UPDATE cm
  SET    newVarID   = iv.VariableID,
		 NewVVID    = iv.VariableID,
		 OutcomeID  = 'NEW',
		 OutcomeVID = 'NEW',
  -- if it is an old cell record in the generation report an old cell (changing Main property of keys) has a new created variable
		 ReportMsg = 'New Variable ID & New Variable VID: ' + (CASE 
															     WHEN cm.isNewCell = 1 THEN 'New Cell'
                                                                 ELSE 'Old cell (changing Main property of keys) has a new created variable' 
															   END)
  FROM   #cellmodelling  cm
  JOIN   #new_Aspects    na ON (na.newAspect  = cm.newAspect) 
  JOIN   #InsertVarID    iv ON (iv.newAspect  = na.newAspect)
  JOIN   VariableVersion vv ON (vv.VariableID = iv.VariableID)
  WHERE  cm.tvStartReleaseID			 = @CurrentRelease
  AND    NewVVID 						 IS NULL
  AND    vv.ENDReleaseID 				 IS NULL
  AND    vv.StartReleaseID				 = @CurrentRelease
  AND    cm.isVoid = 0 ;

-- Other things to provide in the generation report: 
-- All the identical cells (with identical aspects) for all the moduleversions with ENDRelease = null 
-- AND indicate for each ONe if it maintains the same variable or different variables AS well AS all the rest of relevant information mentioned above.

-- First recreate New Aspects for all Cells with moduleVersion.ENDReleaseID=null (i.e. all cells INTO #cellmodelling)
  DROP TABLE IF EXISTS #InsertVarID; 
  
  DROP TABLE IF EXISTS #new_Aspects; 
  DROP TABLE IF EXISTS #all_Aspects;
  
  SELECT cm.NewAspect, 
		 cm.NewKeyID, 
		 cm.NewPropertyID, 
		 cm.newContextID, 
		 (ROW_NUMBER() OVER (ORDER BY cm.NewAspect ASC)) AS AspectID, 
		 COUNT(DISTINCT cellid) 						 AS noofcells
  INTO   #all_Aspects
  FROM   #cellmodelling cm
  --WHERE cm.isVoid=0
  GROUP BY cm.NewAspect, 
		   cm.NewKeyID, 
		   cm.NewPropertyID, 
		   cm.newContextID
  ORDER BY cm.NewAspect;

-- SELECT * FROM #new_aspects order by noofcells desc

-- THIS IS THE OUTPUT REPORT
-- We can always adjust the fields


-- Update TableVersionCell table from cell modelling
-- DECLARE @CurrentRelease int = 2   ---1020000001
UPDATE tvc
SET tvc.VariableVID = cm.newVVID 
FROM TableVersionCell tvc
JOIN #cellmodelling   cm ON tvc.CellID = cm.CellID AND tvc.TableVID = cm.TableVID 
WHERE cm.TvStartReleaseID = @CurrentRelease 
AND   cm.mvStartReleaseID = @CurrentRelease
AND    cm.isVoid = 0


-- Set to All TableVersionCells with isVoid=1 or isExcluded=1 : VariableVID=Null
UPDATE tvc
SET tvc.VariableVID = Null
FROM TableVersionCell tvc INNER JOIN TableVersion tv on tvc.TableVID = tv.TableVID 
WHERE tv.StartReleaseID = @CurrentRelease 
AND   (tvc.isVoid=1 OR tvc.isExcluded=1)



-- Create Aux_CellStatus entries if not existing
-- DECLARE @CurrentRelease int = 2 --1020000001
INSERT INTO Aux_CellStatus (TableVID, CellID, isNewCell, Status)
SELECT distinct cm.TableVID, cm.CellID,cm.isNewCell, CASE WHEN cm.isVoid=1 THEN 'Not reportable' ELSE 'Need to generate' END as Status 
FROM #cellmodelling cm
WHERE cm.TvStartReleaseID=@CurrentRelease AND 
( NOT EXISTS (SELECT cst.* FROM Aux_CellStatus cst WHERE cst.CellID=cm.CellID AND cst.TableVID=cm.TableVID) )


-- Update Aux_CellStatus table from cell modelling
-- DECLARE @CurrentRelease int = 2 --1020000001
UPDATE cst
SET cst.Status = 
CASE WHEN (outcomeid = 'NEW' or outcomeid = 'OTHER NEW') THEN 'New variable' ELSE 
CASE WHEN (outcomevid = 'OLD' or outcomevid = 'OTHER OLD') THEN 'Previous variable version' ELSE 'New variable version' END
END
FROM Aux_CellStatus cst
JOIN #cellmodelling   cm ON cst.CellID = cm.CellID AND cst.TableVID = cm.TableVID 
WHERE cm.TvStartReleaseID = @CurrentRelease 
AND   cm.mvStartReleaseID = @CurrentRelease
AND    cm.isVoid = 0


  INSERT INTO VarGeneration_Detail 
  SELECT na.noofcells,
		 na.NewAspect,
		 cm.ModuleVID, 
		 cm.ModuleCode, 
		 cm.TableCode, 
		 cm.TableVID, 
		 cm.CellID, 
		 cm.cellcode, 
		 cm.outcomeID,
		 cm.outcomeVID,
		 cm.ReportMsg,
		 cm.isVoid, 
		 cm.tvstartReleaseID, 
		 cm.mvStartReleaseID, 
		 cm.vvOldEndReleaseID, 
		 cm.OldAspect, 
		 cm.IsNewCell, 
		 cm.isnewPropertyDataType, 
		 cm.isNewKey, 
		 cm.OldVariableID,
		 cm.NewVarID,
		 cm.OldVariableVID,
		 cm.NewVVID
  FROM   #cellmodelling cm 
  JOIN   #all_Aspects   na ON (cm.NewAspect = na.NewAspect)
  WHERE   cm.isVoid = 0 and outcomeVID<>'OLD'
  ORDER BY noofcells DESC, 
           na.NewAspect, 
		   cm.ModuleCode; --, cm.TableCode, cm.CellCode
    
  INSERT INTO VarGeneration_Summary (outcomeid, outcomevid, ReportMsg, noofcells, mincell, maxcell ) 
  SELECT outcomeid, 
		 outcomevid, 
		 ReportMsg, 
		 COUNT(distinct (str(tablevid)+'_'+str(cellid)))      AS noofcells,  
		 MIN(cellcode) AS mincell, 
		 MAX(cellcode) AS maxcell 
  FROM   #cellmodelling 
  WHERE #cellmodelling.isVoid = 0
  GROUP BY outcomeid, outcomevid, ReportMsg 
  ORDER BY outcomeid desc, outcomevid desc, ReportMsg;

-- In the end of a successful Variable Generation call the cleaning service
execute [dbo].[Cleaning_Service_01]
  
-- Query to group various report messages

-- SELECT reportmsg, count(cellid) AS noofcells FROM #cellmodelling WHERE isvoid=0 group by reportmsg


-- View out put tables

--select * from #output_detail where cellcode like '{C_03.00%' order by cellcode;

--select * from #output_summary;
-- DECLARE @CurrentRelease int = 2
--select distinct OutcomeID, OutcomeVID, ReportMsg, count(*), min(cellcode), max(cellcode) from #cellmodelling group by OutcomeID, OutcomeVID, ReportMsg
--select * from #cellmodelling where cellcode like '{C_27.00%'
--select * from tableversion where tablevid=5836

END; -- Errors in Cell Modelling

  
  --select od.* from #output_detail od where newaspect= '_8288_678554'
  -- od.CellCode IN ('{C_03.00, r0020, c0010}',	'{C_03.00, r0330, c0010}')
  --od.newAspect in (select od2.newaspect from #output_Detail od2 where od2.CellCode='{C_03.00, r0330, c0010}')

END;    -- Check_Modelling_Rules proc

--SELECT (select cx.contextid from context cx where trim(cx.signature)=trim(#cellmodelling.newSignature)) as tobecontext,* FROM #cellmodelling where isvoid=0 and newcontextid is null and newsignature is not null and trim(newsignature)<>'' 
--union  
--SELECT null as tobecontext,* FROM #cellmodelling where isvoid=0 and newcontextid is null and (newsignature is null or trim(newsignature)<>'' )
--cellcode like '{C_99.0%'

-- Clean all temporary tables
  DROP TABLE IF EXISTS #all_Aspects;
  DROP TABLE IF EXISTS #cellmodelling;

--
-- Now reset sequences for all the entities involved in insertions in variable generation
-- Namely: Item, CompoundKey, Context, Variable, VariableVersion 
-- declare @maxContextID int; declare @maxKeyID int; declare @maxItemID int; declare @maxVariableID int; declare @maxVariableVID int 

SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRAN;

    /* =========================
       Context
       ========================= */
    --DECLARE @maxContextID bigint;
    SELECT @maxContextID = ISNULL(MAX(ContextID), 1010000000)
    FROM dbo.[Context]
    WHERE ContextID >= 1010000000;

    -- Add default constraint only if it doesn't already exist
    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        JOIN sys.columns c ON c.default_object_id = dc.object_id
        JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.schema_id = SCHEMA_ID('dbo')
          AND t.name = 'Context'
          AND c.name = 'ContextID'
    )
    BEGIN
        ALTER TABLE dbo.[Context]
        ADD CONSTRAINT DF_Context_ContextID
            DEFAULT (NEXT VALUE FOR dbo.[Seq_Context]) FOR [ContextID];
    END

    -- Restart sequence using dynamic SQL (RESTART WITH requires a literal)
    DECLARE @sql nvarchar(400);
    SET @sql = N'ALTER SEQUENCE dbo.Seq_Context RESTART WITH ' + CONVERT(varchar(30), @maxContextID + 1) + N';';
    EXEC (@sql);


    /* =========================
       Item
       ========================= */
    --DECLARE @maxItemID bigint;
    SELECT @maxItemID = ISNULL(MAX(ItemID), 1010000000)
    FROM dbo.[Item]
    WHERE ItemID >= 1012420000;   -- as per your original lower bound

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        JOIN sys.columns c ON c.default_object_id = dc.object_id
        JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.schema_id = SCHEMA_ID('dbo')
          AND t.name = 'Item'
          AND c.name = 'ItemID'
    )
    BEGIN
        ALTER TABLE dbo.[Item]
        ADD CONSTRAINT DF_Item_ItemID
            DEFAULT (NEXT VALUE FOR dbo.[Seq_Item]) FOR [ItemID];
    END

    SET @sql = N'ALTER SEQUENCE dbo.Seq_Item RESTART WITH ' + CONVERT(varchar(30), @maxItemID + 1) + N';';
    EXEC (@sql);


    /* =========================
       CompoundKey (KeyID)
       ========================= */
    --DECLARE @maxKeyID bigint;
    -- Fixed range: 1,010,000,000 to 1,019,999,999 (assuming 10M block; adjust if needed)
    SELECT @maxKeyID = ISNULL(MAX(KeyID), 1010000000)
    FROM dbo.[CompoundKey]
    WHERE KeyID BETWEEN 1010000000 AND 1019999999;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        JOIN sys.columns c ON c.default_object_id = dc.object_id
        JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.schema_id = SCHEMA_ID('dbo')
          AND t.name = 'CompoundKey'
          AND c.name = 'KeyID'
    )
    BEGIN
        ALTER TABLE dbo.[CompoundKey]
        ADD CONSTRAINT DF_CompoundKey_KeyID
            DEFAULT (NEXT VALUE FOR dbo.[Seq_CompoundKey]) FOR [KeyID];
    END

    SET @sql = N'ALTER SEQUENCE dbo.Seq_CompoundKey RESTART WITH ' + CONVERT(varchar(30), @maxKeyID + 1) + N';';
    EXEC (@sql);


    /* =========================
       Variable (VariableID)
       ========================= */
    --DECLARE @maxVariableID bigint;
    -- Fixed range upper bound
    SELECT @maxVariableID = ISNULL(MAX(VariableID), 1010000000)
    FROM dbo.[Variable]
    WHERE VariableID BETWEEN 1010000000 AND 1019999999;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        JOIN sys.columns c ON c.default_object_id = dc.object_id
        JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.schema_id = SCHEMA_ID('dbo')
          AND t.name = 'Variable'
          AND c.name = 'VariableID'
    )
    BEGIN
        ALTER TABLE dbo.[Variable]
        ADD CONSTRAINT DF_Variable_VariableID
            DEFAULT (NEXT VALUE FOR dbo.[Seq_Variable]) FOR [VariableID];
    END

    SET @sql = N'ALTER SEQUENCE dbo.Seq_Variable RESTART WITH ' + CONVERT(varchar(30), @maxVariableID + 1) + N';';
    EXEC (@sql);


    /* =========================
       VariableVersion (VariableVID)
       ========================= */
    --DECLARE @maxVariableVID bigint;
    -- Fixed range upper bound
    SELECT @maxVariableVID = ISNULL(MAX(VariableVID), 1010000000)
    FROM dbo.[VariableVersion]
    WHERE VariableVID BETWEEN 1010000000 AND 1019999999;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        JOIN sys.columns c ON c.default_object_id = dc.object_id
        JOIN sys.tables t ON t.object_id = c.object_id
        WHERE t.schema_id = SCHEMA_ID('dbo')
          AND t.name = 'VariableVersion'
          AND c.name = 'VariableVID'
    )
    BEGIN
        ALTER TABLE dbo.[VariableVersion]
        ADD CONSTRAINT DF_VariableVersion_VariableVID
            DEFAULT (NEXT VALUE FOR dbo.[Seq_VariableVersion]) FOR [VariableVID];
    END

    SET @sql = N'ALTER SEQUENCE dbo.Seq_VariableVersion RESTART WITH ' + CONVERT(varchar(30), @maxVariableVID + 1) + N';';
    EXEC (@sql);


    COMMIT TRAN;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRAN;

    DECLARE
        @ErrMsg nvarchar(4000) = ERROR_MESSAGE(),
        @ErrNum int = ERROR_NUMBER(),
        @ErrSev int = ERROR_SEVERITY(),
        @ErrSta int = ERROR_STATE(),
        @ErrLin int = ERROR_LINE(),
        @ErrProc nvarchar(200) = ERROR_PROCEDURE();

    RAISERROR('Error %d, Severity %d, State %d, Line %d',
              @ErrSev, 1, @ErrNum, @ErrSev, @ErrSta, @ErrLin);
END CATCH;



END;    -- Variable_Generation_Tidy Proc