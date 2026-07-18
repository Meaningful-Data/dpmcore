
BEGIN 

  IF OBJECT_ID(N'dbo.ModelViolations', N'U') IS NULL CREATE TABLE dbo.ModelViolations (ViolationCode nvarchar(10), 
  																					   Violation nvarchar(255),
  																					   isBlocking bit,
  																					   TableVID  int, 
  																					   OldTableVID int,
  																					   TableCode nvarchar(40), 
  																					   HeaderID int, 
  																					   HeaderCode  nvarchar(30), 
  																					   HeaderVID int, 
  																					   OldHeaderVID int, 
  																					   KeyHeader bit, 
  																					   HeaderDirection nvarchar(1), 
  																					   HeaderPropertyID int, 
  																					   HeaderPropertyCode  nvarchar(20), 
  																					   HeaderSubcategoryID int, 
  																					   HeaderSubcategoryName nvarchar(60), 
  																					   HeaderContextID int,
																					   CategoryID int,
																					   CategoryCode nvarchar(50), 
  																					   ItemID int,
  																					   ItemCode nvarchar(30),
  																					   CellID int,
  																					   CellCode nvarchar(50),
  																					   Cell2ID int,
  																					   Cell2Code nvarchar(50),
  																					   VVEndReleaseID int,
  																					   NewAspect nvarchar(80)
  																					  );


  DELETE FROM ModelViolations;
  
  DECLARE @CurrentRelease int; --- = 2
  
--- DJT Added to make CurrentRelease dynamic
  
  SELECT @CurrentRelease = ReleaseID
  FROM   [dbo].[Release]
  WHERE  ReleaseID=9999;    -- Playground ReleaseID=9999
  

-- 1. Open Row Table must have at least one key Header in Column
  INSERT INTO ModelViolations
  SELECT DISTINCT 
  	     '2_1'								  AS ViolationCode, 
  	     'Open Row Table without Key Columns' AS Violation,
  	     1									  AS isBlocking,
  	     tv.TableVID						  AS TableVID, 
  	     NULL								  AS OldTableVID,
  	     tv.Code							  AS TableCode, 
  	     NULL								  AS HeaderID, 
  	     NULL								  AS HeaderCode, 
  	     NULL								  AS HeaderVID, 
  	     NULL								  AS OldHeaderVID, 
  	     NULL								  AS KeyHeader, 
  	     NULL								  AS HeaderDirection, 
  	     NULL								  AS HeaderPropertyID, 
  	     NULL								  AS HeaderPropertyCode, 
  	     NULL								  AS HeaderSubcategoryID, 
  	     NULL								  AS HeaderSubcategoryName, 
  	     NULL								  AS HeaderContextID, 
  	     NULL								  AS CategoryID, 
  	     NULL								  AS CategoryCode, 
  	     NULL								  AS ItemID,
  	     NULL								  AS ItemCode,
  	     NULL								  AS CellID,
  	     NULL								  AS CellCode,
  	     NULL								  AS Ceell2ID,
  	     NULL								  AS Cell2Code,
  	     NULL								  AS VVEndReleaseID,
  	     NULL								  AS NewAspect
  FROM [TableVersion] tv 
  JOIN [Table]		  t  ON t.TableID=tv.TableID 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE t.IsAbstract=0 
  AND   t.hasOpenRows=1 
  AND   NOT EXISTS (SELECT h.* 
                    FROM Header h  
  				    JOIN tableversionheader tvh ON (tvh.HeaderID=h.HeaderID) 
  				    WHERE tvh.TableVID = tv.TableVID 
  				    AND   h.TableID    = t.TableID 
  				    AND   h.isKey		 = 1 
  				    AND   h.Direction  = 'X' 
  				   ) 
  AND   tv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;

-- 2. Open Column Table must have at least one key Header in Row
  INSERT INTO ModelViolations
  SELECT DISTINCT
		 '2_2'								  AS ViolationCode, 
		 'Open Column Table without Key Rows' AS Violation,
		 1									  AS isBlocking,
		 tv.TableVID						  AS TableVID, 
		 NULL								  AS OldTableVID,
		 tv.Code							  AS TableCode, 
		 NULL								  AS HeaderID, 
		 NULL								  AS HeaderCode, 
		 NULL								  AS HeaderVID, 
		 NULL								  AS OldHeaderVID, 
		 NULL								  AS KeyHeader, 
		 NULL								  AS HeaderDirection, 
		 NULL								  AS HeaderPropertyID, 
		 NULL								  AS HeaderPropertyCode, 
		 NULL								  AS HeaderSubcategoryID, 
		 NULL								  AS HeaderSubcategoryName, 
		 NULL								  AS HeaderContextID, 
  	     NULL								  AS CategoryID, 
  	     NULL								  AS CategoryCode, 
		 NULL								  AS  ItemID,
		 NULL								  AS  ItemCode,
		 NULL								  AS CellID,
		 NULL								  AS CellCode,
		 NULL								  AS Ceell2ID,
		 NULL								  AS Cell2Code,
		 NULL								  AS VVEndReleaseID,
		 NULL								  AS NewAspect
  FROM [TableVersion]  tv 
  JOIN [Table]         t  ON (t.TableID=tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE t.IsAbstract=0 
  AND   t.hasOpenColumns=1 
  AND   NOT EXISTS (SELECT h.* 
                    FROM  Header h  
				    JOIN  TableVersionHeader tvh ON (tvh.HeaderID=h.HeaderID) 
				    WHERE tvh.TableVID = tv.TableVID 
				    AND   h.TableID    = t.TableID 
				    AND   h.isKey=1 
				    AND   h.Direction='Y' 
				   ) 
  AND   tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 3. Open Sheet Table must have at least one key Header in Sheet
  INSERT INTO ModelViolations
  SELECT DISTINCT 
		 '2_3'									AS ViolationCode, 
		 'Open Sheet Table without Key Sheets'	AS Violation,
		 1										AS isBlocking,
		 tv.TableVID							AS TableVID, 
		 NULL									AS OldTableVID,
		 tv.Code								AS TableCode, 
		 NULL									AS HeaderID, 
		 NULL									AS HeaderCode, 
		 NULL									AS HeaderVID, 
		 NULL									AS OldHeaderVID, 
		 NULL									AS KeyHeader, 
		 NULL									AS HeaderDirection, 
		 NULL									AS HeaderPropertyID, 
		 NULL									AS HeaderPropertyCode, 
		 NULL									AS HeaderSubcategoryID, 
		 NULL									AS HeaderSubcategoryName, 
		 NULL									AS HeaderContextID, 
  	     NULL  						  		    AS CategoryID, 
  	     NULL	  							    AS CategoryCode, 
		 NULL									AS ItemID,
		 NULL									AS ItemCode,
		 NULL									AS CellID,
		 NULL									AS CellCode,
		 NULL									AS Ceell2ID,
		 NULL									AS Cell2Code,
		 NULL									AS VVEndReleaseID,
		 NULL									AS NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]        t  ON (t.TableID=tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract    = 0 
  AND	 t.hasOpenSheets = 1 
  AND    NOT EXISTS (SELECT h.* 
                     FROM Header h  
  				     JOIN TableVersionHeader tvh ON (tvh.HeaderID = h.HeaderID) 
  				     WHERE tvh.TableVID = tv.TableVID 
  				     AND   h.TableID    = t.TableID 
  				     AND   h.isKey		= 1 
  				     AND   h.Direction	= 'Z' 
  				    ) 
  AND    tv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;

-- 1b. Open Row Table must have at least one non-key Header in Column

  INSERT INTO ModelViolations
  SELECT DISTINCT 
		 '2_4'										AS ViolationCode, 
		 'Open Row Table without non-Key Columns'	AS Violation,
		 0											AS isBlocking,
		 tv.TableVID								AS TableVID, 
		 NULL										AS OldTableVID,
		 tv.Code									AS TableCode, 
		 NULL										AS HeaderID, 
		 NULL										AS HeaderCode, 
		 NULL										AS HeaderVID, 
		 NULL										AS OldHeaderVID, 
		 NULL										AS KeyHeader, 
		 NULL										AS HeaderDirection, 
		 NULL										AS HeaderPropertyID, 
		 NULL										AS HeaderPropertyCode, 
		 NULL										AS HeaderSubcategoryID, 
		 NULL										AS HeaderSubcategoryName, 
		 NULL										AS HeaderContextID, 
  	     NULL         							    AS CategoryID, 
  	     NULL								        AS CategoryCode, 
		 NULL										AS  ItemID,
		 NULL										AS  ItemCode,
		 NULL										AS CellID,
		 NULL										AS CellCode,
		 NULL										AS Ceell2ID,
		 NULL										AS Cell2Code,
		 NULL										AS VVEndReleaseID,
		 NULL										AS NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]        t  ON (t.TableID = tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract  = 0 
  AND	 t.hasOpenRows = 1 
  AND    NOT EXISTS (SELECT h.* 
                     FROM Header h  
  					 JOIN TableVersionHeader tvh ON (tvh.HeaderID = h.HeaderID) 
  					 WHERE tvh.TableVID = tv.TableVID 
  				     AND   h.TableID    = t.TableID 
  					 AND   h.isKey		= 0 
  					 AND   h.Direction  = 'X' 
  					) 
  AND    tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 2b. Open Column Table must have at least one non-key Header in Row
  INSERT INTO ModelViolations
  SELECT DISTINCT 
	     '2_5'									  AS ViolationCode, 
	     'Open Column Table without non-Key Rows' AS Violation,
	     0										  AS isBlocking,
	     tv.TableVID							  AS TableVID, 
	     NULL									  AS OldTableVID,
	     tv.Code								  AS TableCode, 
	     NULL									  AS HeaderID, 
	     NULL									  AS HeaderCode, 
	     NULL									  AS HeaderVID, 
	     NULL									  AS OldHeaderVID, 
	     NULL									  AS KeyHeader, 
	     NULL									  AS HeaderDirection, 
	     NULL									  AS HeaderPropertyID, 
	     NULL									  AS HeaderPropertyCode, 
	     NULL									  AS HeaderSubcategoryID, 
	     NULL									  AS HeaderSubcategoryName, 
	     NULL									  AS HeaderContextID, 
  	     NULL       							  AS CategoryID, 
  	     NULL								      AS CategoryCode, 
	     NULL									  AS ItemID,
	     NULL									  AS ItemCode,
	     NULL									  AS CellID,
	     NULL									  AS CellCode,
	     NULL									  AS Ceell2ID,
	     NULL									  AS Cell2Code,
	     NULL									  AS VVEndReleaseID,
	     NULL									  AS NewAspect
  FROM  [TableVersion] tv 
  JOIN  [Table]		   t  ON (t.TableID = tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE t.IsAbstract     = 0 
  AND   t.hasOpenColumns = 1 
  AND   NOT EXISTS (SELECT h.* 
                    FROM  Header			 h  
  				    JOIN  TableVersionHeader tvh ON (tvh.HeaderID = h.HeaderID)
  				    WHERE tvh.TableVID = tv.TableVID 
  				    AND   h.TableID    = t.TableID 
  					AND   h.isKey      = 0 
  					AND   h.Direction  = 'Y' 
  					  ) 
  AND tv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;




-- 3b. Table with non-open rows and non-open columns must have at least one Header in Row and at least on Header in column
  INSERT INTO ModelViolations
  SELECT DISTINCT 
		 '2_6'													AS ViolationCode, 
		 'Closed Row & Column Table is missing Rows or Columns' AS Violation,
		 1														AS isBlocking,
		 tv.TableVID											AS TableVID, 
		 NULL													AS OldTableVID,
		 tv.Code												AS TableCode, 
		 NULL													AS HeaderID, 
		 NULL													AS HeaderCode, 
		 NULL													AS HeaderVID, 
		 NULL													AS OldHeaderVID, 
		 NULL													AS KeyHeader, 
		 NULL													AS HeaderDirection, 
		 NULL													AS HeaderPropertyID, 
		 NULL													AS HeaderPropertyCode, 
		 NULL													AS HeaderSubcategoryID, 
		 NULL													AS HeaderSubcategoryName, 
		 NULL													AS HeaderContextID, 
  	     NULL					    							AS CategoryID, 
  	     NULL			 								        AS CategoryCode, 
		 NULL													AS ItemID,
		 NULL													AS ItemCode,
		 NULL													AS CellID,
		 NULL													AS CellCode,
		 NULL													AS Ceell2ID,
		 NULL													AS Cell2Code,
		 NULL													AS VVEndReleaseID,
		 NULL													AS NewAspect
  FROM [TableVersion] tv 
  JOIN [Table]		  t  ON (t.TableID = tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE t.IsAbstract     = 0 
  AND   t.hasOpenColumns = 0
  AND   t.hasOpenRows    = 0
  AND 
  (
   (NOT EXISTS (SELECT h.* 
                FROM   Header h  
  				JOIN   TableVersionHeader tvh ON (tvh.HeaderID = h.HeaderID) 
  				WHERE  tvh.TableVID = tv.TableVID 
  				AND    h.TableID    = t.TableID 
  				AND    h.isKey      = 0 
  				AND    h.Direction  = 'Y' 
  			   )  
   )
  OR
   (NOT EXISTS (SELECT h.* 
                FROM   Header h  
  			    JOIN   tableversionheader tvh ON tvh.HeaderID=h.HeaderID 
  				WHERE  tvh.TableVID = tv.TableVID 
  				AND    h.TableID    = t.TableID 
  				AND    h.isKey      = 0 
  				AND    h.Direction  = 'X' 
  			    ) 
   )
  )
  AND tv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 4.	Key Header Rule: For every Key Header there must obligatorily exist one PropertyID.
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_1'												AS ViolationCode, 
		 'Key Header without any attached Property in it'	AS Violation,
		 1													AS isBlocking,
		 tv.TableVID										AS TableVID, 
		 NULL												AS OldTableVID,
		 tv.Code											AS TableCode, 
		 h.HeaderID											AS HeaderID, 
		 hv.Code											AS HeaderCode, 
		 NULL												AS HeaderVID, 
		 NULL												AS OldHeaderVID, 
		 1													AS KeyHeader, 
		 NULL												AS HeaderDirection, 
		 NULL												AS HeaderPropertyID, 
		 NULL												AS HeaderPropertyCode, 
		 NULL												AS HeaderSubcategoryID, 
		 NULL												AS HeaderSubcategoryName, 
		 NULL												AS HeaderContextID, 
  	     NULL       							            AS CategoryID, 
  	     NULL								                AS CategoryCode, 
		 NULL												AS ItemID,
		 NULL												AS ItemCode,
		 NULL												AS CellID,
		 NULL												AS CellCode,
		 NULL												AS Ceell2ID,
		 NULL												AS Cell2Code,
		 NULL												AS VVEndReleaseID,
		 NULL												AS NewAspect
  FROM [TableVersion]		tv 
  JOIN [Table]				t	ON (t.TableID    = tv.TableID) 
  JOIN [Header]				h	ON (t.TableID    = h.TableID) 
  JOIN [HeaderVersion]		hv	ON (h.HeaderID   = hv.HeaderID)
  JOIN [TableVersionHeader] tvh ON (
									tvh.TableVID = tv.TableVID 
								  AND 
								    tvh.HeaderID = h.HeaderID 
								   )
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE t.IsAbstract	= 0 
  AND   h.isKey			= 1
  AND	hv.PropertyID	IS NULL
  AND	tv.EndReleaseID IS NULL
  AND	hv.EndReleaseID is NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 5.	Key Headers are only allowed if they are not Abstract Headers
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_2'												AS ViolationCode, 
		 'Key Header declared as Abstract is not allowed'	AS Violation,
		 1													AS isBlocking,
		 tv.TableVID										AS TableVID, 
		 NULL												AS OldTableVID,
		 tv.Code											AS TableCode, 
		 h.HeaderID											AS HeaderID, 
		 hv.Code											AS HeaderCode, 
		 NULL												AS HeaderVID, 
		 NULL												AS OldHeaderVID, 
		 1													AS KeyHeader, 
		 NULL												AS HeaderDirection, 
		 NULL												AS HeaderPropertyID, 
		 NULL												AS HeaderPropertyCode, 
		 NULL												AS HeaderSubcategoryID, 
		 NULL												AS HeaderSubcategoryName, 
		 NULL												AS HeaderContextID, 
  	     NULL       							            AS CategoryID, 
  	     NULL								                AS CategoryCode, 
		 NULL												AS ItemID,
		 NULL												AS ItemCode,
		 NULL												AS CellID,
		 NULL												AS CellCode,
		 NULL												AS Ceell2ID,
		 NULL												AS Cell2Code,
		 NULL												AS VVEndReleaseID,
		 NULL												AS NewAspect
  FROM [TableVersion]		tv 
  JOIN [Table]				t	ON (t.TableID    = tv.TableID) 
  JOIN [Header]				h	ON (t.TableID    = h.TableID) 
  JOIN [HeaderVersion]		hv	ON (h.HeaderID   = hv.HeaderID) 
  JOIN [TableVersionHeader] tvh ON (
									tvh.TableVID = tv.TableVID 
								  AND 
								    tvh.HeaderID = h.HeaderID 
								   )
  WHERE t.IsAbstract    = 0
  AND   tvh.IsAbstract  = 1
  AND   h.isKey         = 1
  AND   tv.EndReleaseID IS NULL 
  AND	hv.EndReleaseID is NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 6.	Main Property single Axis full Coverage Rule
-- 6.a. All Main Properties (ex-Metrics) should be accommodated in a single Table axis (including the whole Table). Moreover on this Axis All non-Abstract and non-key Headers have to be associated to a non-Null Property.
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3 
  SELECT DISTINCT 
		 '2_10'														AS ViolationCode, 
		 'Table has Main Properties Assigned to more than one Axes' AS Violation,
		 1															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 NULL														AS OldTableVID,
		 tv.Code													AS TableCode, 
		 NULL														AS HeaderID, 
		 NULL														AS HeaderCode, 
		 NULL														AS HeaderVID, 
		 NULL														AS OldHeaderVID, 
		 NULL														AS KeyHeader, 
		 NULL														AS HeaderDirection, 
		 NULL														AS HeaderPropertyID, 
		 NULL														AS HeaderPropertyCode, 
		 NULL														AS HeaderSubcategoryID, 
		 NULL														AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     NULL        							                    AS CategoryID, 
  	     NULL								                        AS CategoryCode, 
		 NULL														AS ItemID,
		 NULL														AS ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]		t	ON (t.TableID = tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract    = 0
  AND    tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  AND 1  < ( 
            (
             SELECT COUNT(DISTINCT h.Direction) 
  			 FROM   Header h 
  			 JOIN   HeaderVersion		hv	on (h.HeaderID   = hv.HeaderID) 
  			 JOIN   TableVersionHeader	tvh on (
												tvh.TableVID = tv.TableVID 
											  AND 
											    tvh.HeaderVID = hv.HeaderVID 
											   )
  			 WHERE t.TableID      = h.TableID  
			 and	hv.EndReleaseID is NULL 
  			 AND   tvh.IsAbstract = 0
  			 AND   h.isKey		  = 0
  			 AND   hv.PropertyID	IS NOT NULL
  		    )
  		  + (CASE 
		       WHEN tv.PropertyID IS NOT NULL THEN 1 
			   ELSE 0 
			 END
			)
  		  ) 
  AND 
  tv.StartReleaseID = @CurrentRelease  
  ORDER BY tv.TableVID;

-- 6.b. There must be exactly One Axis where Main Properties are Assigned. If no Axis exists then report Violation
  INSERT INTO ModelViolations 
 --DECLARE @CurrentRelease int = 3   
  SELECT DISTINCT 
		 '2_11'														AS ViolationCode, 
		 'Table has Not any Main Properties Assigned to any Axes'	AS Violation,
		 1															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 NULL														AS OldTableVID,
		 tv.Code													AS TableCode, 
		 NULL														AS HeaderID, 
		 NULL														AS HeaderCode, 
		 NULL														AS HeaderVID, 
		 NULL														AS OldHeaderVID, 
		 NULL														AS KeyHeader, 
		 NULL														AS HeaderDirection, 
		 NULL														AS HeaderPropertyID, 
		 NULL														AS HeaderPropertyCode, 
		 NULL														AS HeaderSubcategoryID, 
		 NULL														AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     NULL       	   						                    AS CategoryID, 
  	     NULL								                        AS CategoryCode, 
		 NULL														AS ItemID,
		 NULL														AS ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [TableVersion]	tv
  JOIN   [Table]		t	ON (t.TableID = tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND 0 = ( 
		   (
            SELECT COUNT(DISTINCT h.Direction) 
  			FROM   [Header]			    h 
  			JOIN   [HeaderVersion]	    hv  ON (h.HeaderID   = hv.HeaderID) 
  			JOIN   [TableVersionHeader] tvh ON (
											    tvh.TableVID = tv.TableVID 
											  AND 
											    tvh.HeaderVID=hv.HeaderVID
											   )
  			WHERE 
			t.TableID			 = h.TableID  
  			AND   tvh.IsAbstract = 0
  			AND	  h.isKey        = 0
			AND hv.EndReleaseID is NULL 
  			AND   hv.PropertyID  IS NOT NULL
  		   )
  		  + 
		   (CASE 
		      WHEN tv.PropertyID IS NOT NULL THEN 1 
			  ELSE 0 
			END
		   )
  		  )
  ORDER BY tv.TableVID;

-- 6.c. On the Axis where one Main Property is Assigned All the non-Abstract & Non-Key Headers must havea Main Property Assignment
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '2_12'																												AS ViolationCode, 
		 'Not all non-Abstract and non-key headers of the axis to which main properties are assigned have a main property'	AS Violation,
		 1																													AS isBlocking,
		 tv.TableVID																										AS TableVID, 
		 NULL																												AS OldTableVID,
		 tv.Code																											AS TableCode, 
		 NULL																												AS HeaderID, 
		 NULL																												AS HeaderCode, 
		 NULL																												AS HeaderVID, 
		 NULL																												AS  OldHeaderVID, 
		 NULL																												AS KeyHeader, 
		 h.Direction																										AS HeaderDirection, 
		 NULL																												AS HeaderPropertyID, 
		 NULL																												AS HeaderPropertyCode, 
		 NULL																												AS HeaderSubcategoryID, 
		 NULL																												AS HeaderSubcategoryName, 
		 NULL																												AS HeaderContextID, 
  	     NULL       																										AS CategoryID, 
  	     NULL																												AS CategoryCode, 
		 NULL																												AS ItemID,
		 NULL																												AS ItemCode,
		 NULL																												AS CellID,
		 NULL																												AS CellCode,
		 NULL																												AS Ceell2ID,
		 NULL																												AS Cell2Code,
		 NULL																												AS VVEndReleaseID,
		 NULL																												AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN   [Header]				h	ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
								        tvh.HeaderVID	= hv.HeaderVID 
									  AND 
										tvh.TableVID	= tv.TableVID
									   )
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract    = 0
  AND	 tv.EndReleaseID IS NULL 
  AND	 hv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		 = 0
  AND	 tvh.isAbstract  = 0
  AND	 hv.PropertyID   IS NOT NULL
  AND	 EXISTS (SELECT hv2.* 
  				 FROM   Header				h2 
  				 JOIN   HeaderVersion		hv2	 ON (h2.HeaderID = hv2.HeaderID) 
  				 JOIN   TableVersionHeader	tvh2 ON (
													 tvh2.TableVID  = tv.TableVID 
												   AND 
												     tvh2.HeaderVID = hv2.HeaderVID 
													)
  				 WHERE  t.TableID		 = h2.TableID  
  				 AND	tvh2.IsAbstract	 = 0
  				 AND	h2.isKey		 = 0
  				 AND	h2.Direction	 = h.Direction
  				 AND	hv2.EndReleaseID IS NULL
  				 AND	hv2.PropertyID   IS NULL 
				)
  ORDER BY tv.TableVID, 
		   h.Direction;


-- 6d Variant: If a Main Property has been assigned to a whole table it has to be isMetric=1 
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '2_13'															AS ViolationCode, 
		 'Main Property Assigned to a Whole Table that is Not a Metric' AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 NULL															AS HeaderID, 
		 NULL															AS HeaderCode, 
		 NULL															AS HeaderVID, 
		 NULL															AS  OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 NULL															AS HeaderDirection, 
		 tv.PropertyID													AS HeaderPropertyID, 
		 itc.Code														AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     c.CategoryID  													AS CategoryID, 
  	     c.Code															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM	 [TableVersion] tv 
  JOIN   [Table]		t	 ON (t.TableID		= tv.TableID) 
  JOIN   [ItemCategory] itc  ON (tv.PropertyID	= itc.ItemID) 
  JOIN   Property		p	 ON (itc.ItemID		= p.PropertyID) 
  JOIN   PropertyCategory pc ON (pc.PropertyID	= p.PropertyID) 
  JOIN   Category c			 ON (pc.CategoryID	= c.CategoryID) 
  JOIN [ModuleVersionComposition] mvc ON mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv ON mv.ModuleVID = mvc.ModuleVID
  WHERE  tv.EndReleaseID IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 tv.PropertyID	 IS NOT NULL
  AND	 p.IsMetric		 = 0
  AND	pc.EndReleaseID is NULL
  ORDER BY tv.TableVID;


-- 7.	Main property (ex-Metric) Assigned to sheet has to be isMetric = 1. 
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_3'													AS ViolationCode, 
		 'Main Property on Sheet Header that is Not a Metric'	AS Violation,
		 0														AS isBlocking,
		 tv.TableVID											AS TableVID, 
		 NULL													AS OldTableVID,
		 tv.Code												AS TableCode, 
		 h.HeaderID												AS HeaderID, 
		 hv.Code												AS HeaderCode, 
		 NULL													AS HeaderVID, 
		 NULL													AS OldHeaderVID, 
		 NULL													AS KeyHeader, 
		 h.Direction											AS HeaderDirection, 
		 NULL													AS HeaderPropertyID, 
		 NULL													AS HeaderPropertyCode, 
		 NULL													AS HeaderSubcategoryID, 
		 NULL													AS HeaderSubcategoryName, 
		 NULL													AS HeaderContextID, 
  	     c.CategoryID  											AS CategoryID, 
  	     c.Code													AS CategoryCode, 
		 NULL													AS ItemID,
		 NULL													AS ItemCode,
		 NULL													AS CellID,
		 NULL													AS CellCode,
		 NULL													AS Ceell2ID,
		 NULL													AS Cell2Code,
		 NULL													AS VVEndReleaseID,
		 NULL													AS NewAspect
  FROM	 [TableVersion]			tv 
  JOIN	 [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN	 [Header]				h	ON (h.TableID		= t.TableID) 
  JOIN	 [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN	 [TableVersionHeader]	tvh ON (
		 								tvh.HeaderVID	= hv.HeaderVID 
		 							  AND 
		 							    tvh.TableVID	= tv.TableVID
		 							   )
  JOIN	 [Property]				p	ON (p.PropertyID	= hv.PropertyID)
  JOIN   PropertyCategory pc ON (pc.PropertyID	= p.PropertyID) 
  JOIN   Category c			 ON (pc.CategoryID	= c.CategoryID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL 
  AND	 hv.EndReleaseID	IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey			= 0
  AND	 h.Direction		= 'Z'
  AND	 tvh.isAbstract		= 0
  AND	 hv.PropertyID		IS NOT NULL
  AND	 p.isMetric			= 0 
  AND	pc.EndReleaseID is NULL
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;


		   
-- 8.	Check if Main Property in one Header exists in Key of the same Table
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '4_1'																				as ViolationCode, 
		 'Main Property in this Header  exists also as Key Property on the same Table'	as Violation,
		 1																					as isBlocking,
		 tv.TableVID																		as TableVID, 
		 NULL																				as OldTableVID,
		 tv.Code																			as TableCode, 
		 h.HeaderID     																	as HeaderID, 
		 hv.Code																			as HeaderCode, 
		 hv.HeaderVID   																	as HeaderVID, 
		 NULL																				as OldHeaderVID, 
		 NULL																				as KeyHeader, 
		 NULL																				as HeaderDirection, 
		 hv.PropertyID																		as HeaderPropertyID, 
		 itc.Code																			as HeaderPropertyCode, 
		 NULL																				as HeaderSubcategoryID, 
		 NULL																				as HeaderSubcategoryName, 
		 NULL																				as HeaderContextID, 
  	     c.CategoryID  																		AS CategoryID, 
  	     c.Code																				AS CategoryCode, 
		 NULL																				as ItemID,
		 NULL																				as ItemCode,
		 NULL																				as CellID,
		 NULL																				as CellCode,
		 NULL																				as Ceell2ID,
		 NULL																				as Cell2Code,
		 NULL																				as VVEndReleaseID,
		 NULL																				as NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]		t	ON (t.TableID  = tv.TableID) 
  JOIN   [Header] h         ON (h.TableID = t.TableID)
  JOIN   [HeaderVersion] hv ON (hv.HeaderID = h.HeaderID) 
  JOIN   [TableVersionHeader] tvh ON (tvh.TableVID = tv.TableVID  and tvh.HeaderVID = hv.HeaderVID) 
  JOIN   [ItemCategory] itc ON (itc.ItemID = hv.PropertyID) 
  JOIN   PropertyCategory pc ON (pc.PropertyID	= hv.PropertyID) 
  JOIN   Category c			 ON (pc.CategoryID	= c.CategoryID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract	 = 0
  AND    tv.EndReleaseID IS NULL 
  AND    hv.EndReleaseID IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND    hv.PropertyID is not Null
  AND    tvh.IsAbstract = 0 
  AND    h.IsKey = 0 
  AND itc.EndReleaseID is NULL 
  AND pc.EndReleaseID is NULL
  AND hv.PropertyID in (SELECT hv2.PropertyID 
  			  FROM	 Header				h2 
  			  JOIN	 HeaderVersion		hv2	 ON (h2.HeaderID    = hv2.HeaderID) 
  			  JOIN	 TableVersionHeader tvh2 ON (
												 tvh2.TableVID  = tv.TableVID 
											   AND 
											     tvh2.HeaderVID = hv2.HeaderVID
												)
  			  WHERE  t.TableID		  = h2.TableID  
  			  AND	 tvh2.IsAbstract  = 0
  			  AND	 h2.isKey		  = 1
  			  AND	 hv2.EndReleaseID IS NULL
  			 )
  ORDER BY tv.TableVID


-- 8.	Check if Main Property on a WHOLE TABLE exists in Key of the same Table BUT THIS IS HERE when: TV.PropertyID is not Null
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '4_1'																				as ViolationCode, 
		 'Main Property in this Header (or whole Table) exists also as Key Property on the same Table'	as Violation,
		 1																					as isBlocking,
		 tv.TableVID																		as TableVID, 
		 NULL																				as OldTableVID,
		 tv.Code																			as TableCode, 
		 NULL																				as HeaderID, 
		 NULL																				as HeaderCode, 
		 NULL																				as HeaderVID, 
		 NULL																				as OldHeaderVID, 
		 NULL																				as KeyHeader, 
		 NULL																				as HeaderDirection, 
		 tv.PropertyID																		as HeaderPropertyID, 
		 itc.Code																			as HeaderPropertyCode, 
		 NULL																				as HeaderSubcategoryID, 
		 NULL																				as HeaderSubcategoryName, 
		 NULL																				as HeaderContextID, 
  	     c.CategoryID       																AS CategoryID, 
  	     c.Code																				AS CategoryCode, 
		 NULL																				as ItemID,
		 NULL																				as ItemCode,
		 NULL																				as CellID,
		 NULL																				as CellCode,
		 NULL																				as Ceell2ID,
		 NULL																				as Cell2Code,
		 NULL																				as VVEndReleaseID,
		 NULL																				as NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]		t	ON (t.TableID  = tv.TableID) 
  JOIN   [ItemCategory] itc ON (itc.ItemID = tv.PropertyID)
  JOIN   PropertyCategory pc ON (pc.PropertyID	= tv.PropertyID) 
  JOIN   Category c			 ON (pc.CategoryID	= c.CategoryID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract	 = 0
  AND    tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  AND   tv.PropertyID is not Null
  AND	itc.EndReleaseID is NULL
  AND   pc.EndReleaseID is NULL
  AND EXISTS (SELECT hv2.* 
  			  FROM	 Header				h2 
  			  JOIN	 HeaderVersion		hv2	 ON (h2.HeaderID    = hv2.HeaderID) 
  			  JOIN	 TableVersionHeader tvh2 ON (
												 tvh2.TableVID  = tv.TableVID 
											   AND 
											     tvh2.HeaderVID = hv2.HeaderVID
												)
  			  WHERE  t.TableID		  = h2.TableID  
  			  AND	 tvh2.IsAbstract  = 0
  			  AND	 h2.isKey		  = 1
  			  AND	 hv2.PropertyID = tv.PropertyID
  			  AND	 hv2.EndReleaseID IS NULL
  			 )
  ORDER BY tv.TableVID


		  
-- 9.	Check if more than one Headers have Same Main Property and Same Context together
  INSERT INTO ModelViolations 
--DECLARE @CurrentRelease int = 2  
  SELECT DISTINCT 
		 '4_2'																					AS ViolationCode, 
		 'This combination of Main PropertyID and ContextID appears in more than one Headers'	AS Violation,
		 0																						AS isBlocking,
		 tv.TableVID																			AS TableVID, 
		 NULL																					AS OldTableVID,
		 tv.Code																				AS TableCode, 
		 h.HeaderID																				AS HeaderID, 
		 hv.Code																				AS HeaderCode, 
		 NULL																					AS HeaderVID, 
		 NULL																					AS OldHeaderVID, 
		 NULL																					AS KeyHeader, 
		 h.Direction																			AS HeaderDirection, 
		 hv.PropertyID																			AS HeaderPropertyID, 
		 itc.Code																				AS HeaderPropertyCode, 
		 NULL																					AS HeaderSubcategoryID, 
		 NULL																					AS HeaderSubcategoryName, 
		 hv.ContextID																			AS HeaderContextID, 
  	     c.CategoryID  																			AS CategoryID, 
  	     c.Code																					AS CategoryCode, 
		 NULL																					AS  ItemID,
		 NULL																					AS  ItemCode,
		 NULL																					AS CellID,
		 NULL																					AS CellCode,
		 NULL																					AS Ceell2ID,
		 NULL																					AS Cell2Code,
		 NULL																					AS VVEndReleaseID,
		 NULL																					AS NewAspect
  FROM			  [TableVersion]		tv 
  JOIN			  [Table]				t	ON (t.TableID     = tv.TableID) 
  JOIN			  [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN			  [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN			  [Header]				h	ON (h.TableID     = t.TableID)
  JOIN			  [HeaderVersion]		hv	ON (hv.HeaderID   = h.HeaderID)
  JOIN			  [TableVersionHeader]	tvh ON (
												tvh.HeaderVID = hv.HeaderVID 
											  AND 
											    tvh.TableVID  = tv.TableVID
											   )

  LEFT OUTER JOIN [ItemCategory]		itc ON (itc.ItemID    = hv.PropertyID)
  LEFT OUTER JOIN PropertyCategory pc ON (pc.PropertyID	= hv.PropertyID) 
  LEFT OUTER JOIN  Category c			 ON (pc.CategoryID	= c.CategoryID) 
  WHERE t.IsAbstract    = 0
  AND	tv.EndReleaseID IS NULL 
  AND   hv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	h.isKey		 = 0
  AND	tvh.isAbstract	 = 0
  AND	itc.EndReleaseID is NULL
  AND   pc.EndReleaseID is NULL 
  -- SOS! Ask if needed to include this line
  --AND   (
--		 hv.PropertyID IS NOT NULL 
--		OR 
--		 hv.ContextID  IS NOT NULL
--		)
  AND EXISTS (SELECT hv2.* 
  			  FROM   Header				h2 
  			  JOIN   HeaderVersion		hv2	 ON (h2.HeaderID    = hv2.HeaderID) 
  			  JOIN   TableVersionHeader tvh2 ON (
												 tvh2.TableVID  = tv.TableVID 
											   AND 
											     tvh2.HeaderVID = hv2.HeaderVID 
												)
  			  WHERE  t.TableID				   = h2.TableID  
  			  AND    hv.HeaderID			  != hv2.HeaderID
  			  AND    tvh2.IsAbstract		   = 0
  			  AND    h2.isKey				   = 0
  			  AND    ISNULL(hv2.PropertyID,-1) = ISNULL(hv.PropertyID,-1)
  			  AND    ISNULL(hv2.ContextID,-1)  = ISNULL(hv.ContextID,-1)
  			  AND    hv2.EndReleaseID IS NULL
  		     )
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;



-- 10a.	Main Property coincidence as Context: First check Context of Headers only
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
  SELECT DISTINCT 
		 '4_3'																				AS ViolationCode, 
		 'Main Property in this Header exists also as Context Property on the same Table'	AS Violation,
		 1																					AS isBlocking,
		 tv.TableVID																		AS TableVID, 
		 Null																				AS OldTableVID,
		 tv.Code																			AS TableCode, 
		 h.HeaderID																			AS HeaderID, 
		 hv.Code																			AS HeaderCode, 
		 Null																				AS HeaderVID, 
		 Null																				AS  OldHeaderVID, 
		 Null																				AS KeyHeader, 
		 h.Direction																		AS HeaderDirection, 
		 hv.PropertyID																		AS HeaderPropertyID, 
		 itc.Code																			AS HeaderPropertyCode, 
		 Null																				AS HeaderSubcategoryID, 
		 Null																				AS HeaderSubcategoryName, 
		 Null																				AS HeaderContextID, 
  	     c.CategoryID  																		AS CategoryID, 
  	     c.Code																				AS CategoryCode, 
		 Null																				AS ItemID,
		 Null																				AS ItemCode,
		 Null																				AS CellID,
		 Null																				AS CellCode,
		 Null																				AS Ceell2ID,
		 Null																				AS Cell2Code,
		 Null																				AS VVEndReleaseID,
		 Null																				AS NewAspect
  FROM			  [TableVersion]		tv 
  JOIN			  [Table]				t	ON (t.TableID	  = tv.TableID) 
  JOIN			  [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN			  [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN			  [Header]				h	ON (h.TableID	  = t.TableID) 
  JOIN			  [HeaderVersion]		hv	ON (hv.HeaderID   = h.HeaderID)
  JOIN			  [TableVersionHeader]	tvh	ON (
												tvh.HeaderVID = hv.HeaderVID 
											  AND 
											    tvh.TableVID  = tv.TableVID
											   )
  LEFT OUTER JOIN [ItemCategory]		itc ON (itc.ItemID	  = hv.PropertyID)
  LEFT OUTER JOIN   PropertyCategory pc ON (pc.PropertyID	= hv.PropertyID) 
  LEFT oUTER JOIN   Category c			 ON (pc.CategoryID	= c.CategoryID) 

  WHERE t.IsAbstract    = 0
  AND	tv.EndReleaseID IS NULL 
  AND   hv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	h.isKey			= 0
  AND	tvh.isAbstract	= 0
  AND	hv.PropertyID	IS NOT NULL 
  AND itc.EndReleaseID is NULL
  AND pc.EndReleaseID is NULL
  AND   EXISTS (SELECT NULL
				FROM   [TableVersionHeader] tvh2
				JOIN   [TableVersion]       tv2 ON (tv2.TableVID = tvh2.TableVID)
				JOIN   [Header]             h2  ON (h2.TableID   = tv2.TableID)
				JOIN   [HeaderVersion]      hv2 ON (hv2.HeaderID = h2.HeaderID)
				JOIN   [ContextComposition] cc2 ON (cc2.ContextID = hv2.ContextID AND cc2.PropertyID = hv.PropertyID)
				WHERE  tvh2.TableVID = tv.TableVID
				AND    tvh2.IsAbstract = 0
				AND    h2.IsKey        = 0
				AND	   (h2.Direction<>h.Direction OR h2.HeaderID=h.HeaderID)
				AND    hv2.EndReleaseID IS NULL
  		  	   ) 
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;  



-- 10b.	Main Property coincidence as Context: Secondly check Context of whole table
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '4_3'																				AS ViolationCode, 
		 'Main Property in this Header exists also as Context Property on the same Table'	AS Violation,
		 1																					AS isBlocking,
		 tv.TableVID																		AS TableVID, 
		 Null																				AS OldTableVID,
		 tv.Code																			AS TableCode, 
		 h.HeaderID																			AS HeaderID, 
		 hv.Code																			AS HeaderCode, 
		 Null																				AS HeaderVID, 
		 Null																				AS  OldHeaderVID, 
		 Null																				AS KeyHeader, 
		 h.Direction																		AS HeaderDirection, 
		 hv.PropertyID																		AS HeaderPropertyID, 
		 itc.Code																			AS HeaderPropertyCode, 
		 Null																				AS HeaderSubcategoryID, 
		 Null																				AS HeaderSubcategoryName, 
		 Null																				AS HeaderContextID, 
  	     c.CategoryID  																		AS CategoryID, 
  	     c.Code																				AS CategoryCode, 
		 Null																				AS ItemID,
		 Null																				AS ItemCode,
		 Null																				AS CellID,
		 Null																				AS CellCode,
		 Null																				AS Ceell2ID,
		 Null																				AS Cell2Code,
		 Null																				AS VVEndReleaseID,
		 Null																				AS NewAspect
  FROM			  [TableVersion]		tv 
  JOIN			  [Table]				t	ON (t.TableID	  = tv.TableID) 
  JOIN			  [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN			  [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN			  [Header]				h	ON (h.TableID	  = t.TableID) 
  JOIN			  [HeaderVersion]		hv	ON (hv.HeaderID   = h.HeaderID)
  JOIN			  [TableVersionHeader]	tvh	ON (
												tvh.HeaderVID = hv.HeaderVID 
											  AND 
											    tvh.TableVID  = tv.TableVID
											   )
  LEFT OUTER JOIN [ItemCategory]		itc ON (itc.ItemID	  = hv.PropertyID) 
  LEFT OUTER JOIN   PropertyCategory	pc  ON (pc.PropertyID = hv.PropertyID) 
  LEFT OUTER JOIN   Category			c   ON (pc.CategoryID = c.CategoryID) 

  WHERE t.IsAbstract    = 0
  AND	tv.EndReleaseID IS NULL
  AND   hv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	h.isKey			= 0
  AND	tvh.isAbstract	= 0
  AND	hv.PropertyID	IS NOT NULL 
  AND itc.EndReleaseID is NULL 
  AND pc.EndReleaseID is NULL
  AND   EXISTS (SELECT NULL
  		        FROM   [ContextComposition] cc2 
  		        WHERE  cc2.ContextID   = ISNULL(tv.ContextID, -1)
  		        AND    cc2.PropertyID  = hv.PropertyID 
  		  	   )
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;  




-- 11.	New header version is the same as the previous version 
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 4  
  SELECT DISTINCT 
		 '1_1'														AS ViolationCode, 
		 'This Header has Current Version same as Previous Version' AS Violation,
		 1															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 Null														AS OldTableVID,
		 tv.Code													AS TableCode, 
		 h.HeaderID													AS HeaderID, 
		 hv.Code													AS HeaderCode, 
		 hv.HeaderVID												AS HeaderVID, 
		 hv2.HeaderVID												AS OldHeaderVID, 
		 Null														AS KeyHeader, 
		 h.Direction												AS HeaderDirection, 
		 Null														AS HeaderPropertyID, 
		 Null														AS HeaderPropertyCode, 
		 Null														AS HeaderSubcategoryID, 
		 Null														AS HeaderSubcategoryName, 
		 Null														AS HeaderContextID, 
  	     NULL       												AS CategoryID, 
  	     NULL														AS CategoryCode, 
		 Null														AS ItemID,
		 Null														AS ItemCode,
		 Null														AS CellID,
		 Null														AS CellCode,
		 Null														AS Ceell2ID,
		 Null														AS Cell2Code,
		 Null														AS VVEndReleaseID,
		 Null														AS NewAspect
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
  ORDER BY tv.TableVID, 
		   hv.Code;


-- 12.	The new table version is the same as the previous version

--.	If there does not exist header version duplication:
--	if all the headers used in this new table version is the old header version (startRelease != currentRelease), then we need to check the table version duplication, 
-- in this case, we only need to check that everything is same in TableVersion, TableVersionHeader  (all information) and TableVersionCell (all information except vvid)
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 4
  SELECT DISTINCT 
		 '1_2'																		AS ViolationCode, 
		 'This Table Version fields are the same as Previous Table Version fields'  AS Violation,
		 1																			AS isBlocking,
		 tv.TableVID																AS TableVID, 
		 tv2.TableVID																AS OldTableVID,
		 tv.Code																	AS TableCode, 
		 NULL																		AS HeaderID, 
		 NULL																		AS HeaderCode, 
		 NULL																		AS HeaderVID, 
		 NULL																		AS OldHeaderVID, 
		 NULL																		AS KeyHeader, 
		 NULL																		AS HeaderDirection, 
		 NULL																		AS HeaderPropertyID, 
		 NULL																		AS HeaderPropertyCode, 
		 NULL																		AS HeaderSubcategoryID, 
		 NULL																		AS HeaderSubcategoryName, 
		 NULL																		AS HeaderContextID, 
  	     NULL  																		AS CategoryID, 
  	     NULL																		AS CategoryCode, 
		 NULL																		AS ItemID,
		 NULL																		AS ItemCode,
		 NULL																		AS CellID,
		 NULL																		AS CellCode,
		 NULL																		AS Ceell2ID,
		 NULL																		AS Cell2Code,
		 NULL																		AS VVEndReleaseID,
		 NULL																		AS NewAspect
  FROM   [TableVersion] tv 
  JOIN	 [Table]		t	ON (t.TableID   = tv.TableID)
  JOIN	 [TableVersion] tv2 ON (tv2.TableID = t.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract	  = 0 
  AND	 tv.EndReleaseID  IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	 tv2.EndReleaseID = tv.StartReleaseID 
  AND    ISNULL(tv.Code, '!!!')   = ISNULL(tv2.Code, '!!!') 
  AND    ISNULL(tv.[Name], '!!!') = ISNULL(tv2.[Name], '!!!')
  AND    ISNULL(tv.ContextID, -1) = ISNULL(tv2.ContextID, -1) 
  AND	 ISNULL(tv.PropertyID,-1) = ISNULL(tv2.PropertyID, -1) 
  AND	 ISNULL(tv.KeyID,-1)      = ISNULL(tv2.KeyID, -1) 
  AND ( 
       (SELECT COUNT(*) 
        FROM [TableVersionHeader] tvh3 
  	    WHERE tvh3.TableVID = tv.TableVID
  	   ) 
  	   = 
  	   (SELECT COUNT(*) 
  	    FROM  [TableVersionHeader] tvh4 
  		WHERE tvh4.TableVID = tv2.TableVID
  	   ) 
  	  ) 
  AND (
       NOT EXISTS  (SELECT * 
					FROM			[TableVersionHeader]	tvh  
  					JOIN			[Header]				h		ON (h.HeaderID     = tvh.HeaderID) 
  					JOIN			[HeaderVersion]			hv		ON (tvh.HeaderVID  = hv.HeaderVID) 
  					LEFT OUTER JOIN [TableVersionHeader]	tvh2	ON (
																		tv2.TableVID   = tvh2.TableVID 
																	  AND 
																		tvh.HeaderID   = tvh2.HeaderID 
																	   )
  					LEFT OUTER JOIN [HeaderVersion]			hv2		ON (tvh2.HeaderVID = hv2.HeaderVID) 
  					WHERE  tv.TableVID=tvh.TableVID 
  				    AND (
   					     (ISNULL(tvh.HeaderID,-999999999) <> ISNULL(tvh2.HeaderID,-999999999)) 
   				      OR 
					     (ISNULL(tvh.HeaderVID,-999999999) <> ISNULL(tvh2.HeaderVID,-999999999)) 
					  OR
					     (ISNULL(tvh.ParentHeaderID,-999999999) <> ISNULL(tvh2.ParentHeaderID,-999999999)) 
					  OR
					     (ISNULL(tvh.[Order],-999999999) <> ISNULL(tvh2.[Order],-999999999))  
					  OR 
					     (tvh.isAbstract<>tvh2.isAbstract) 

					  OR
					     (tvh.isUnique <>tvh2.isUnique) 
					  OR
					     (ISNULL(hv.[Code],'-111111111')<>ISNULL(hv2.[Code],'-111111111'))
					  OR 
       				     (ISNULL(hv.[Label],'-11111')<>ISNULL(hv2.[Label],'-11111'))
					  OR 
					     (ISNULL(hv.ContextID,-999999999)<>ISNULL(hv2.ContextID,-999999999)) 
					  OR 
					     (ISNULL(hv.PropertyID,-999999999)<>ISNULL(hv2.PropertyID,-999999999)) 
					  OR 
					     (ISNULL(hv.SubCategoryVID,-999999999)<>ISNULL(hv2.SubCategoryVID,-999999999)) 
                       ) 
  			       ) 
		)
  
  AND (   
       (
	    SELECT COUNT(*) 
		FROM   TableVersionCell tvc3 
		WHERE   tvc3.TableVID  =  tv.TableVID
	   ) 
       = 
	   (
	    SELECT COUNT(*) 
		FROM TableVersionCell tvc4 
		WHERE tvc4.TableVID=tv2.TableVID
	   ) 
  	  )  
  AND (
       NOT EXISTS  ( SELECT * 
                     FROM			 TableVersionCell tvc 
  					 JOIN			 Cell			  ce   ON (ce.CellID = tvc.CellID) 
                     LEFT OUTER JOIN TableVersionCell tvc2 ON (ce.CellID = tvc2.CellID)
                     WHERE tv.TableVID  = tvc.TableVID 
					 AND   tv2.TableVID = tvc2.TableVID 
  			         AND  ( 
						    (ISNULL(tvc.CellCode,'-1')<>ISNULL(tvc2.CellCode,'-1')) 
						 OR 
						    (tvc.isNullable<>tvc2.isNullable) 
						 OR 
						    (tvc.isExcluded<>tvc2.isExcluded) 
						 OR 
						    (tvc.isVoid<>tvc2.isVoid) 
						 OR 
						    (ISNULL(tvc.Sign,'-5')<>ISNULL(tvc2.Sign,'-5')) 
                          )
                   ) 
      )
  ORDER BY tv.TableVID;

-- Test specific table versions header by header
--select hv.code, hv2.code, hv.label, hv2.label, len(hv.label), len(hv2.label), hv.startreleaseid, hv.endreleaseid, hv2.StartReleaseID, hv2.EndReleaseID  
--from headerversion hv inner join headerversion hv2 on hv.HeaderID=hv2.headerid 
--inner join tableversionheader tvh on tvh.headervid=hv.headervid 
--inner join tableversionheader tvh2 on tvh2.headervid=hv2.headervid 
--where tvh.TableVID=2228 and tvh2.TableVID=5836
--order by hv.code


-- 13. Closed Row Table must NOT have at all Key Headers in Column
  INSERT INTO ModelViolations
  SELECT DISTINCT 
  	     '2_7'									AS ViolationCode, 
  	     'Closed Row Table with Key Columns'	AS Violation,
  	     1										AS isBlocking,
  	     tv.TableVID							AS TableVID, 
  	     NULL									AS OldTableVID,
  	     tv.Code								AS TableCode, 
  	     NULL									AS HeaderID, 
  	     NULL									AS HeaderCode, 
  	     NULL									AS HeaderVID, 
  	     NULL									AS OldHeaderVID, 
  	     NULL									AS KeyHeader, 
  	     NULL									AS HeaderDirection, 
  	     NULL									AS HeaderPropertyID, 
  	     NULL									AS HeaderPropertyCode, 
  	     NULL									AS HeaderSubcategoryID, 
  	     NULL									AS HeaderSubcategoryName, 
  	     NULL									AS HeaderContextID, 
  	     NULL       							AS CategoryID, 
  	     NULL									AS CategoryCode, 
  	     NULL									AS ItemID,
  	     NULL									AS ItemCode,
  	     NULL									AS CellID,
  	     NULL									AS CellCode,
  	     NULL									AS Ceell2ID,
  	     NULL									AS Cell2Code,
  	     NULL									AS VVEndReleaseID,
  	     NULL									AS NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]		t  ON (t.TableID = tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract   = 0 
  AND	 t.hasOpenRows  = 0 
  AND    EXISTS (SELECT h.* 
                 FROM   [Header]				h  
  			     JOIN   [TableVersionHeader]	tvh ON (tvh.HeaderID = h.HeaderID) 
  			     WHERE  tvh.TableVID = tv.TableVID 
  			     AND    h.TableID    = t.TableID 
  			     AND    h.isKey	   = 1 
  			     AND    h.Direction  = 'X' 
  			    ) 
  AND    tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;



-- 14. Closed Column Table must NOT have at all Key Headers in Row
  INSERT INTO ModelViolations
  SELECT DISTINCT 
		 '2_8'									AS ViolationCode, 
		 'Closed Column Table with Key Rows'	AS Violation,
		 1										AS isBlocking,
		 tv.TableVID							AS TableVID, 
		 NULL									AS OldTableVID,
		 tv.Code								AS TableCode, 
		 NULL									AS HeaderID, 
		 NULL									AS HeaderCode, 
		 NULL									AS HeaderVID, 
		 NULL									AS OldHeaderVID, 
		 NULL									AS KeyHeader, 
		 NULL									AS HeaderDirection, 
		 NULL									AS HeaderPropertyID, 
		 NULL									AS HeaderPropertyCode, 
		 NULL									AS HeaderSubcategoryID, 
		 NULL									AS HeaderSubcategoryName, 
		 NULL									AS HeaderContextID, 
  	     NULL       							AS CategoryID, 
  	     NULL									AS CategoryCode, 
		 NULL									AS ItemID,
		 NULL									AS ItemCode,
		 NULL									AS CellID,
		 NULL									AS CellCode,
		 NULL									AS Ceell2ID,
		 NULL									AS Cell2Code,
		 NULL									AS VVEndReleaseID,
		 NULL									AS NewAspect
  FROM   [TableVersion] tv 
  JOIN   [Table]		t  ON (t.TableID = tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract     = 0 
  AND    t.HasOpenColumns = 0 
  AND EXISTS (SELECT h.* 
              FROM  [Header]				h  
  			  JOIN  [TableVersionHeader]	tvh ON (tvh.HeaderID = h.HeaderID)
  			  WHERE tvh.TableVID = tv.TableVID 
  			  AND   h.TableID    = t.TableID 
  			  AND   h.isKey      = 1 
  			  AND   h.Direction  = 'Y' 
  			 ) 
  AND tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 15. Closed Sheet Table must NOT have at all Key Headers in Sheet
  INSERT INTO ModelViolations
  SELECT DISTINCT 
		 '2_9'								 AS ViolationCode, 
		 'Closed Sheet Table with Key Sheet' AS Violation,
		 1									 AS isBlocking,
		 tv.TableVID						 AS TableVID, 
		 NULL								 AS OldTableVID,
		 tv.Code							 AS TableCode, 
		 NULL								 AS HeaderID, 
		 NULL								 AS HeaderCode, 
		 NULL								 AS HeaderVID, 
		 NULL								 AS OldHeaderVID, 
		 NULL								 AS KeyHeader, 
		 NULL								 AS HeaderDirection, 
		 NULL								 AS HeaderPropertyID, 
		 NULL								 AS HeaderPropertyCode, 
		 NULL								 AS HeaderSubcategoryID, 
		 NULL								 AS HeaderSubcategoryName, 
		 NULL								 AS HeaderContextID, 
  	     NULL       						 AS CategoryID, 
  	     NULL								 AS CategoryCode, 
		 NULL								 AS ItemID,
		 NULL								 AS ItemCode,
		 NULL								 AS CellID,
		 NULL								 AS CellCode,
		 NULL								 AS Ceell2ID,
		 NULL								 AS Cell2Code,
		 NULL								 AS VVEndReleaseID,
		 NULL								 AS NewAspect
  FROM	 [TableVersion] tv 
  JOIN	 [Table]		t  ON (t.TableID = tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  t.IsAbstract    = 0 
  AND    t.HasOpenSheets = 0 
  AND    EXISTS (SELECT h.* 
                 FROM Header h  
  			     JOIN TableVersionHeader tvh ON (tvh.HeaderID = h.HeaderID) 
  			     WHERE tvh.TableVID = tv.TableVID 
  			     AND h.TableID      = t.TableID 
  			     AND h.isKey        = 1 
  			     AND h.Direction    = 'Z' 
  		        ) 
  AND tv.EndReleaseID IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  ORDER BY tv.TableVID;


-- 16: All Headers of a TableVersion in every ModuleVersion with StartRelease=CurrentRelease must have HeaderVersion.SubCategoryVID.EndRelease=null
-- DECLARE @CurrentRelease int = 2
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_4'													AS ViolationCode, 
		 'SubCategoryVID on this Header has already expired'	AS Violation,
		 1														AS isBlocking,
		 tv.TableVID											AS TableVID, 
		 NULL													AS OldTableVID,
		 tv.Code												AS TableCode, 
		 h.HeaderID												AS HeaderID, 
		 hv.Code												AS HeaderCode, 
		 NULL													AS HeaderVID, 
		 NULL													AS OldHeaderVID, 
		 NULL													AS KeyHeader, 
		 h.Direction											AS HeaderDirection, 
		 NULL													AS HeaderPropertyID, 
		 NULL													AS HeaderPropertyCode, 
		 scv.SubCategoryID										AS HeaderSubcategoryID, 
		 left(sc.Name,60)										AS HeaderSubcategoryName, 
		 NULL													AS HeaderContextID, 
  	     c.CategoryID  											AS CategoryID, 
  	     c.Code													AS CategoryCode, 
		 NULL													AS ItemID,
		 NULL													AS ItemCode,
		 NULL													AS CellID,
		 NULL													AS CellCode,
		 NULL													AS Ceell2ID,
		 NULL													AS Cell2Code,
		 NULL													AS VVEndReleaseID,
		 NULL													AS NewAspect
  FROM   [TableVersion]				tv 
  JOIN   [Table]					t	ON (t.TableID			= tv.TableID) 
  JOIN   [Header]					h	ON (h.TableID			= t.TableID)
  JOIN   [HeaderVersion]			hv	ON (hv.HeaderID			= h.HeaderId)
  JOIN   [TableVersionHeader]		tvh ON (
											tvh.HeaderVID		= hv.HeaderVId 
										  AND 
										    tvh.TableVID		= tv.TableVID
										   )
  JOIN   [subcategoryversion]		scv ON (scv.SubCategoryVID	= hv.SubCategoryVID) 
  JOIN   [SubCategory]				sc	ON (sc.SubCategoryID	= scv.SubCategoryID)
  JOIN   [ModuleVersionComposition]	mvc ON (tv.TableVID			= mvc.TableVID) 
  JOIN   [ModuleVersion]			mv	ON (mv.ModuleVID		= mvc.ModuleVID)
  JOIN   Category c						ON (sc.CategoryID	= c.CategoryID) 

  WHERE  t.IsAbstract		= 0
  AND    tv.EndReleaseID	IS NULL
  AND    hv.EndReleaseID	IS NULL
  AND    mv.StartReleaseID	= @CurrentRelease 
  AND    hv.SubCategoryVID	IS NOT NULL 
  AND	 scv.EndReleaseID	IS NOT NULL
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;



-- 17: On a TableVersion with EndRelease=Null all related HeaderVersions  with EndRelease=Null must have Unique HeaderVersion.Code on each direction X, Y, Z
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '4_4'								AS ViolationCode, 
		 'This Header Code is duplicate'	AS Violation,
		 1									AS isBlocking,
		 tv.TableVID						AS TableVID, 
		 NULL								AS OldTableVID,
		 tv.Code							AS TableCode, 
		 h.HeaderID							AS HeaderID, 
		 hv.Code							AS HeaderCode, 
		 NULL								AS HeaderVID, 
		 NULL								AS OldHeaderVID, 
		 NULL								AS KeyHeader, 
		 h.Direction						AS HeaderDirection, 
		 NULL								AS HeaderPropertyID, 
		 NULL								AS HeaderPropertyCode, 
		 NULL								AS HeaderSubcategoryID, 
		 NULL								AS HeaderSubcategoryName, 
		 NULL								AS HeaderContextID, 
  	     NULL       						AS CategoryID, 
  	     NULL								AS CategoryCode, 
		 NULL								AS ItemID,
		 NULL								AS ItemCode,
		 NULL								AS CellID,
		 NULL								AS CellCode,
		 NULL								AS Ceell2ID,
		 NULL								AS Cell2Code,
		 NULL								AS VVEndReleaseID,
		 NULL								AS NewAspect
  FROM   [TableVersion]				tv 
  JOIN   [Table]					t	ON (t.TableID			= tv.TableID) 
  JOIN   [Header]					h	ON (h.TableID			= t.TableID) 
  JOIN   [HeaderVersion]			hv	ON (hv.HeaderID			= h.HeaderID)
  JOIN   [TableVersionHeader]		tvh ON (
											tvh.HeaderVID		= hv.HeaderVID 
										  AND 
										    tvh.TableVID		= tv.TableVID 
										   )
  JOIN   [ModuleVersionComposition] mvc ON (tv.TableVID			= mvc.TableVID) 
  JOIN   [ModuleVersion]			mv	ON (mv.ModuleVID		= mvc.ModuleVID)
  WHERE  t.IsAbstract    = 0
  AND	 tv.EndReleaseID is null
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	 hv.EndReleaseID is null
  AND   (EXISTS (SELECT * 
                 FROM   [TableVersionHeader] tvh2 
  				 JOIN   [HeaderVersion]		 hv2	ON (tvh2.HeaderVID = hv2.HeaderVID) 
  				 JOIN   [Header]			 h2		ON (hv2.HeaderID   = h2.HeaderID)
                 WHERE  tvh2.TableVID	 = tvh.TableVID 
  			     AND    hv2.EndReleaseID IS NULL 
  				 AND    hv2.HeaderVID	!= hv.HeaderVID 
  				 AND    hv2.Code		 = hv.Code 
  				 AND    h2.Direction	 = h.Direction
  		        )
         )
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;


--18 It is Not recommended to have Abstract Headers without any descendants. , i.e. Every TableVersionHeader that has no descendants has to be isAbstract=0
  INSERT INTO ModelViolations 
--DECLARE @CurrentRelease int = 4  
  SELECT DISTINCT 
		 '3_5'																AS ViolationCode, 
		 'Abstract Header has not at all non-Abstract Descendant headers'	AS Violation,
		 1																	AS isBlocking,
		 tv.TableVID														AS TableVID, 
		 NULL																AS OldTableVID,
		 tv.Code															AS TableCode, 
		 h.HeaderID															AS HeaderID, 
		 hv.Code															AS HeaderCode, 
		 NULL																AS HeaderVID, 
		 NULL																AS OldHeaderVID, 
		 NULL																AS KeyHeader, 
		 h.Direction														AS HeaderDirection, 
		 NULL																AS HeaderPropertyID, 
		 NULL																AS HeaderPropertyCode, 
		 NULL																AS HeaderSubcategoryID, 
		 NULL																AS HeaderSubcategoryName, 
		 NULL																AS HeaderContextID, 
  	     NULL       														AS CategoryID, 
  	     NULL																AS CategoryCode, 
		 NULL																AS ItemID,
		 NULL																AS ItemCode,
		 NULL																AS CellID,
		 NULL																AS CellCode,
		 NULL																AS Ceell2ID,
		 NULL																AS Cell2Code,
		 NULL																AS VVEndReleaseID,
		 NULL																AS NewAspect
  FROM   [TableVersion]				tv 
  JOIN   [Table]					t	ON (t.TableID			= tv.TableID) 
  JOIN   [Header]					h	ON (h.TableID			= t.TableID) 
  JOIN   [HeaderVersion]			hv	ON (hv.HeaderID			= h.HeaderID)
  JOIN   [TableVersionHeader]		tvh ON (
										    tvh.HeaderVID		= hv.HeaderVID 
										  AND 
										    tvh.TableVID=tv.TableVID 
										   )
  JOIN   [ModuleVersionComposition] mvc ON (tv.TableVID			= mvc.TableVID) 
  JOIN   [ModuleVersion]			mv	ON (mv.ModuleVID		= mvc.ModuleVID)
  WHERE  t.IsAbstract    = 0
  AND	 mv.EndReleaseID IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 hv.EndReleaseID IS NULL
  AND	 tvh.isAbstract  = 1 
  AND    NOT EXISTS ( SELECT * 
                      FROM   [TableVersionHeader] tvh2 
  				      WHERE  tvh2.TableVID		 = tv.TableVID 
  				      AND    tvh2.ParentHeaderID = tvh.HeaderID
  				    ) 
  ORDER BY tv.TableVID, 
           h.Direction, 
		   h.HeaderID;



-- 19.	Only non-Metric Properties are allowed for Key Headers, i.e. . Property.isMetric=0
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_6'										AS ViolationCode, 
		 'Key Header with Metric Property attached' AS Violation,
		 1											AS isBlocking,
		 tv.TableVID								AS TableVID, 
		 NULL										AS OldTableVID,
		 tv.Code									AS TableCode, 
		 NULL										AS HeaderID, 
		 NULL										AS HeaderCode, 
		 NULL										AS HeaderVID, 
		 NULL										AS  OldHeaderVID, 
		 NULL										AS KeyHeader, 
		 h.Direction								AS HeaderDirection, 
		 hv.PropertyID								AS HeaderPropertyID, 
		 itc.Code									AS HeaderPropertyCode, 
		 NULL										AS HeaderSubcategoryID, 
		 NULL										AS HeaderSubcategoryName, 
		 NULL										AS HeaderContextID, 
  	     c.CategoryID  								AS CategoryID, 
  	     c.Code										AS CategoryCode, 
		 NULL										AS  ItemID,
		 NULL										AS  ItemCode,
		 NULL										AS CellID,
		 NULL										AS CellCode,
		 NULL										AS Ceell2ID,
		 NULL										AS Cell2Code,
		 NULL										AS VVEndReleaseID,
		 NULL										AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN	 [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN	 [Header]				h	ON (h.TableID		= t.TableID) 
  JOIN	 [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN	 [TableVersionHeader]	tvh ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
										tvh.TableVID	= tv.TableVID
									   )
  JOIN	 [Property]				p	ON (p.PropertyID	= hv.PropertyID)
  JOIN	 [ItemCategory]			itc ON (itc.ItemID		= hv.PropertyID)
  JOIN   PropertyCategory pc ON (pc.PropertyID	= hv.PropertyID) 
  JOIN   Category c			 ON (pc.CategoryID	= c.CategoryID) 

  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	is null 
  AND	 hv.EndReleaseID	is null
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey			= 1
  AND	 tvh.isAbstract		= 0
  AND	 hv.PropertyID		IS NOT NULL
  AND	 p.IsMetric			= 1 
  AND itc.EndReleaseID      is NULL
  AND pc.EndReleaseID       is NULL
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   itc.Code;


-- 20.	Properties in Key Headers must not be assigned to other Key Headers
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_7'															AS ViolationCode, 
		 'Property in Key Header is also assigned to Other Key Header'	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 hv.HeaderID													AS HeaderID, 
		 hv.Code														AS HeaderCode, 
		 hv.HeaderVID													AS HeaderVID, 
		 hv2.HeaderVID													AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 hv.PropertyID													AS HeaderPropertyID, 
		 itc.Code														AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     c.CategoryID  													AS CategoryID, 
  	     c.Code															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t   ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h   ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
		  								tvh.HeaderVID	= hv.HeaderVID 
		  							  AND 
		  								tvh.TableVID	= tv.TableVID
		  							   ) 
  JOIN   [HeaderVersion]		hv2 ON (hv2.PropertyID	= hv.PropertyID) 
  JOIN   [Header]				h2  ON (h2.HeaderID		= hv2.HeaderID)
  JOIN   [ItemCategory]			itc ON (itc.ItemID		= hv.PropertyID)
  JOIN   PropertyCategory		pc  ON (pc.PropertyID	= hv.PropertyID) 
  JOIN   Category            	c	ON (pc.CategoryID	= c.CategoryID) 

  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND	 hv.EndReleaseID	IS NULL
  AND	 hv2.EndReleaseID	IS NULL
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey			= 1
  AND	 h2.IsKey			= 1
  AND	 tvh.isAbstract		= 0
  AND	 hv.PropertyID		IS NOT NULL
  AND	 hv2.PropertyID		IS NOT NULL
  AND	 hv.HeaderVID		< hv2.HeaderVID 
  AND    itc.EndReleaseID   is NULL 
  AND	 pc.EndReleaseID    is NULL
  AND	 EXISTS (SELECT * 
                 FROM   [TableVersionHeader] tvh2 
  				 WHERE  tvh2.TableVID  = tvh.TableVID 
  				 AND	tvh2.HeaderVID = hv2.HeaderVID 
				)
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   hv.Code;


-- 21.	Properties in Key Headers must not be assigned to any ContextComposition.PropertyID for all the HeaderVersions of this TableVersionHeader. 
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_8'															AS ViolationCode, 
		 'Property exists in Key Header and Context of the Same Table'	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 h.HeaderID														AS HeaderID, 
		 hv.Code														AS HeaderCode, 
		 NULL															AS HeaderVID, 
		 NULL															AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 hv.PropertyID													AS HeaderPropertyID, 
		 itc.Code														AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     c.CategoryID  													AS CategoryID, 
  	     c.Code															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM			  [TableVersion]		tv 
  JOIN			  [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN			  [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN			  [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN			  [Header]				h	ON (h.TableID		= t.TableID)
  JOIN			  [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN			  [TableVersionHeader]	tvh ON (
												tvh.HeaderVID	= hv.HeaderVID 
											  AND 
											    tvh.TableVID	= tv.TableVID
											   )
  LEFT OUTER JOIN [ItemCategory]		itc ON (itc.ItemID		= hv.PropertyID) 
  LEFT OUTER JOIN   PropertyCategory	pc	ON (pc.PropertyID	= hv.PropertyID) 
  LEFT OUTER JOIN   Category			c 	ON (pc.CategoryID	= c.CategoryID) 

  WHERE   t.IsAbstract		= 0
  AND	  tv.EndReleaseID	IS NULL
  AND     tv.StartReleaseID = @CurrentRelease 
  AND	  h.isKey			= 1
  AND	  tvh.isAbstract	= 0
  AND	  hv.PropertyID		IS NOT NULL 
  AND	  itc.EndReleaseID  is NULL 
  AND	  pc.EndReleaseID   is NULL 
  AND	  EXISTS (SELECT cc2.* 
  				  FROM   [ContextComposition]   cc2 
  				  JOIN   [HeaderVersion]		hv2  ON (cc2.ContextID = hv2.ContextID)
  				  JOIN   [Header]			    h2   ON (h2.HeaderID   = hv2.HeaderID) 
  				  JOIN   [TableVersionHeader]   tvh2 ON (
														  tvh2.TableVID  = tv.TableVID 
														AND 
														  tvh2.HeaderVID = hv2.HeaderVID 
														)
  				  WHERE t.TableID			= h2.TableID  
  				  AND   tvh2.IsAbstract		= 0
  				  AND   h2.isKey			= 0
  				  AND   cc2.PropertyID		= hv.PropertyID
  				  AND   hv2.EndReleaseID	IS NULL
  				  UNION
  				  SELECT cc2.* 
  				  FROM   [ContextComposition] cc2 
  				  WHERE  tv.ContextID   iS NOT NULL
  				  AND    tv.ContextID   = cc2.ContextID
  				  AND    cc2.PropertyID = hv.PropertyID
  		  		 )
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;


-- 22a.	Properties in ContextComposition of any Header (in TableVersionHeader) 
-- must not be already assigned to ContextComposition.PropertyID of another Header.Direction of the same TableVersion.
-- First check Header Directions only
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
  SELECT DISTINCT 
		 '4_5'																										AS ViolationCode, 
		 'Property in table Context has already been assigned to the Context of another Direction of this Table'	AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 itc.Code																									AS HeaderPropertyCode, 
		 NULL																										AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID  																								AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM	 [TableVersion]			tv 
  JOIN	 [Table]				t	ON (t.TableID		= tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN	 [Header]				h	ON (h.TableID		= t.TableID)
  JOIN	 [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN	 [TableVersionHeader]	tvh ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN	 [ContextComposition]	cc	ON (hv.ContextID	= cc.ContextID)
  JOIN	 [ItemCategory]			itc ON (itc.ItemID		= cc.PropertyID) 
  JOIN   PropertyCategory pc		ON (pc.PropertyID	= cc.PropertyID) 
  JOIN   Category c					ON (pc.CategoryID	= c.CategoryID) 

  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		 = 0
  AND	 tvh.isAbstract  = 0
  AND	 itc.EndReleaseID is NULL
  AND	 pc.EndReleaseID  is NULL
  AND    cc.PropertyID IN (SELECT cc2.PropertyID 
              		       FROM   [ContextComposition]	cc2 
  		                   JOIN   [HeaderVersion]		hv2		ON (cc2.ContextID	= hv2.ContextID )
                           JOIN   [Header]				h2		ON (h2.HeaderID		= hv2.HeaderID)
               		       JOIN   [TableVersionHeader]	tvh2	ON (
						   										    tvh2.TableVID	= tv.TableVID 
						   									      AND 
						   									        tvh2.HeaderVID  = hv2.HeaderVID
						   									       )
  		                   WHERE t.TableID			= h2.TableID  
  		                   AND   tvh2.IsAbstract	= 0
  		                   AND   h2.isKey			= 0
  		                   AND   h2.Direction	   != h.Direction
  		                   AND   hv2.EndReleaseID  IS NULL
  		  		          )
  ORDER BY tv.TableVID
  

  -- 22b.	Properties in ContextComposition of any Header (in TableVersionHeader) 
-- must not be already assigned to ContextComposition.PropertyID of another Header.Direction of the same TableVersion.
-- Secondly check Whole Table Context only
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '4_5'																										AS ViolationCode, 
		 'Property in table Context has already been assigned to the Context of another Direction of this Table'	AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 itc.Code																									AS HeaderPropertyCode, 
		 NULL																										AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID  																								AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM	 [TableVersion]			tv 
  JOIN	 [Table]				t	ON (t.TableID		= tv.TableID)
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN	 [Header]				h	ON (h.TableID		= t.TableID)
  JOIN	 [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN	 [TableVersionHeader]	tvh ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN	 [ContextComposition]	cc	ON (hv.ContextID	= cc.ContextID)
  JOIN	 [ItemCategory]			itc ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory		pc  ON (pc.PropertyID	= cc.PropertyID) 
  JOIN   Category				c	ON (pc.CategoryID	= c.CategoryID) 

  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL 
  AND   tv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		 = 0
  AND	 tvh.isAbstract  = 0 
  AND    itc.EndReleaseID is NULL 
  AND    pc.EndReleaseID  is NULL
  AND    cc.PropertyID IN (SELECT cc2.PropertyID 
  					       FROM   [ContextComposition] cc2 
  					       WHERE  tv.ContextID IS NOT NULL
  					       AND    tv.ContextID = cc2.ContextID
  		  		          )
  ORDER BY tv.TableVID
  


-- 23.	For each HeaderVersion where SubcategoryVID is Not Null: 
-- (PropertyCategory isEnumerated=1 AND SubCategory.CategoryID=PropertyCategory.CategoryID ) OR (PropertyCategory=’_NA’ and SubCategory.Category=’_PR’)
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '3_9'																			AS ViolationCode, 
		 'The Category of SubCategory is Not Compatible with the Category of Property'	AS Violation,
		 1																				AS isBlocking,
		 tv.TableVID																	AS TableVID, 
		 Null																			AS OldTableVID,
		 tv.Code																		AS TableCode, 
		 h.HeaderID																		AS HeaderID, 
		 hv.Code																		AS HeaderCode, 
		 Null																			AS HeaderVID, 
		 Null																			AS  OldHeaderVID, 
		 Null																			AS KeyHeader, 
		 h.Direction																	AS HeaderDirection, 
		 hv.PropertyID																	AS HeaderPropertyID, 
		 itc.Code   																	AS HeaderPropertyCode, 
		 scv.SubCategoryID																AS HeaderSubcategoryID, 
		 left(sc.Name,60)																AS HeaderSubcategoryName, 
		 Null																			AS HeaderContextID, 
  	     Null		  																	AS CategoryID, 
  	     Null  																			AS CategoryCode, 
		 Null																			AS ItemID,
		 Null																			AS ItemCode,
		 Null																			AS CellID,
		 Null																			AS CellCode,
		 Null																			AS Ceell2ID,
		 Null																			AS Cell2Code,
		 Null																			AS VVEndReleaseID,
		 Null																			AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t	ON (t.TableID			= tv.TableID)
  JOIN	 [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN   [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h	ON (h.TableID			= t.TableID) 
  JOIN   [HeaderVersion]		hv	ON (hv.HeaderID			= h.HeaderID) 
  JOIN   [TableVersionHeader]	tvh ON (
										tvh.HeaderVID		= hv.HeaderVID 
									  AND 
									    tvh.TableVID		= tv.TableVID 
									   )
  JOIN   [subcategoryversion]	scv ON (scv.SubCategoryVID	= hv.SubCategoryVID) 
  JOIN   [SubCategory]			sc	ON (sc.SubCategoryID	= scv.SubCategoryID)
  JOIN   [PropertyCategory]		pc1 ON (pc1.PropertyID		= hv.PropertyID) 
  JOIN   [Category]				c1	ON (pc1.CategoryID		= c1.CategoryID) 
  JOIN   [Category]				c2	ON (sc.CategoryID		= c2.CategoryID) 
  JOIN	 [ItemCategory]         itc ON (itc.ItemID          = hv.PropertyID)
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 hv.PropertyID		IS NOT NULL
  AND	 hv.SubCategoryVID	IS NOT NULL 
  AND	 scv.EndReleaseID	IS NULL 
  AND    itc.EndReleaseID   IS NULL
  AND   (
         NOT (
              (
			   c1.CategoryID   = c2.CategoryID 
			 AND 
			   c1.isEnumerated = 1 
			 AND 
			   c2.isEnumerated = 1
			  )
            OR 
  			  (
			   c1.Code='_NA' 
			 AND 
			   c2.Code IN ('_NA', '_PR') 
			  )
             )
  	    )  
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderId;


-- 24.	Only Properties whose Current PropertyCategory.CategoryID isEnumerated=1 can be assigned in ContextComposition.
-- DECLARE @CurrentRelease int = 2  
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '4_6'														AS ViolationCode, 
		 'Non-enumerated Property Assigned to Context Composition'	AS Violation,
		 1															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 NULL														AS OldTableVID,
		 NULL														AS TableCode, 
		 NULL														AS HeaderID, 
		 NULL														AS HeaderCode, 
		 NULL														AS HeaderVID, 
		 NULL														AS  OldHeaderVID, 
		 NULL														AS KeyHeader, 
		 NULL														AS HeaderDirection, 
		 NULL														AS HeaderPropertyID, 
		 itc.Code													AS HeaderPropertyCode, 
		 NULL														AS HeaderSubcategoryID, 
		 NULL														AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     c.CategoryID  												AS CategoryID, 
  	     c.Code														AS CategoryCode, 
		 NULL														AS  ItemID,
		 NULL														AS  ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h	ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   [ContextComposition]	cc	ON (hv.ContextID	= cc.ContextID) 
  JOIN   [ItemCategory]			itc ON (itc.ItemID		= cc.PropertyID)
  JOIN   [PropertyCategory]		pc	ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   [Category]				c	ON (pc.CategoryID	= c.CategoryID) 
  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		 = 0
  AND	 tvh.isAbstract  = 0
  AND	 c.IsEnumerated != 1 
  AND    pc.EndReleaseID is NULL
  AND    itc.EndReleaseID is NULL
  ORDER BY tv.TableVID


-- 25.	PropertyCategory.CategoryID=ItemCategory.CategoryID where PropertyCategory.EndReleaseID=null and ItemCategory.EndReleaseID=null and PropertyCategory should not be a SuperCategory
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
		 '4_7'																									AS ViolationCode, 
		 left('Property Category ('+ sq.PropertyCategoryCode + ') and Item Category (' +sq.ItemCategoryCode+') assignments are not the same',255)	AS Violation,
		 1																										AS isBlocking,
		 sq.TableVID																							AS TableVID, 
		 NULL																									AS OldTableVID,
		 left(trim(sq.TableCode),40)																			AS TableCode, 
		 NULL																									AS HeaderID, 
		 left(trim(sq.HeaderCode),30)																			AS HeaderCode, 
		 NULL																									AS HeaderVID, 
		 NULL																									AS OldHeaderVID, 
		 NULL																									AS KeyHeader, 
		 NULL																									AS HeaderDirection, 
		 sq.PropertyID																									AS HeaderPropertyID, 
		 sq.PropertyCode																						AS HeaderPropertyCode, 
		 NULL																									AS HeaderSubcategoryID, 
		 NULL																									AS HeaderSubcategoryName, 
		 NULL																									AS HeaderContextID, 
  	     NULL       																							AS CategoryID, 
  	     NULL																									AS CategoryCode, 
		 sq.ItemID																								AS ItemID,
		 sq.ItemCode																							AS ItemCode,
		 NULL																									AS CellID,
		 NULL																									AS CellCode,
		 NULL																									AS Ceell2ID,
		 NULL																									AS Cell2Code,
		 NULL																									AS VVEndReleaseID,
		 NULL																									AS NewAspect
  FROM
  (
  (SELECT tv.TableVID, tv.Code as TableCode, h.Direction+'_'+hv.Code as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]			h		ON (h.TableID		= t.TableID)
  JOIN   HeaderVersion		hv		ON (hv.HeaderID		= h.HeaderID)
  JOIN   TableVersionHeader tvh		ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   ContextComposition cc		ON (hv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID) 
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		   = 0
  AND	 tvh.isAbstract    = 0 
  AND rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	
	   ( itc2.EndReleaseID IS NULL 
       AND 
		 pc.EndReleaseID IS NULL 
       AND 
		 itc.EndReleaseID IS NULL 
  	   AND
	     pc.CategoryID	   != itc2.CategoryID )
  )
  UNION
  (SELECT 0, 'CompoundItemID: '+cast(it0.ItemID as nvarchar)+'  CompoundItemCode: '+left(ic0.Code,13) as TableCode, NULL as HeaderCode, 
  cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   Item it0 
  JOIN [ItemCategory] ic0			ON it0.ItemID = ic0.ItemID 
  JOIN [CompoundItemContext] cic0	ON it0.ItemID = cic0.ItemID 
  JOIN   ContextComposition cc		ON (cic0.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  ic0.EndReleaseID is NULL
  AND	 cic0.EndReleaseID   IS NULL
  AND    cic0.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	
	   ( itc2.EndReleaseID IS NULL 
       AND 
		 pc.EndReleaseID IS NULL 
       AND 
		 itc.EndReleaseID IS NULL 
  	   AND
	     pc.CategoryID	   != itc2.CategoryID )
  )

  UNION
  (SELECT tv.TableVID, tv.Code as TableCode, 'Table_Context' as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   ContextComposition cc		ON (tv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND   mv.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND		   ( itc2.EndReleaseID IS NULL 
       AND 
		 pc.EndReleaseID IS NULL 
       AND 
		 itc.EndReleaseID IS NULL 
  	   AND
	     pc.CategoryID	   != itc2.CategoryID )
  
  )

  ) sq
  ORDER BY sq.TableVID;



-- 25b.	PropertyCategory.EndReleaseID is NOTE NULLin a context
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
		 '4_7b'																									AS ViolationCode, 
		 left('Property Category ('+ sq.PropertyCategoryCode + ') has Expired',255) AS Violation,
		 1																										AS isBlocking,
		 sq.TableVID																							AS TableVID, 
		 NULL																									AS OldTableVID,
		 left(trim(sq.TableCode),40)																			AS TableCode, 
		 NULL																									AS HeaderID, 
		 left(trim(sq.HeaderCode),30)																			AS HeaderCode, 
		 NULL																									AS HeaderVID, 
		 NULL																									AS OldHeaderVID, 
		 NULL																									AS KeyHeader, 
		 NULL																									AS HeaderDirection, 
		 sq.PropertyID																									AS HeaderPropertyID, 
		 sq.PropertyCode																						AS HeaderPropertyCode, 
		 NULL																									AS HeaderSubcategoryID, 
		 NULL																									AS HeaderSubcategoryName, 
		 NULL																									AS HeaderContextID, 
  	     NULL       																							AS CategoryID, 
  	     NULL																									AS CategoryCode, 
		 NULL																									AS ItemID,
		 NULL																									AS ItemCode,
		 NULL																									AS CellID,
		 NULL																									AS CellCode,
		 NULL																									AS Ceell2ID,
		 NULL																									AS Cell2Code,
		 NULL																									AS VVEndReleaseID,
		 NULL																									AS NewAspect
  FROM
  (
  (SELECT tv.TableVID, tv.Code as TableCode, h.Direction+'_'+hv.Code as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]			h		ON (h.TableID		= t.TableID)
  JOIN   HeaderVersion		hv		ON (hv.HeaderID		= h.HeaderID)
  JOIN   TableVersionHeader tvh		ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   ContextComposition cc		ON (hv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID) 
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		   = 0
  AND	 tvh.isAbstract    = 0 
  AND rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	pc.EndReleaseID IS NOT NULL 
  )
  UNION
  (SELECT 0, 'CompoundItemID: '+cast(it0.ItemID as nvarchar)+'  CompoundItemCode: '+left(ic0.Code,13) as TableCode, NULL as HeaderCode, 
  cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   Item it0 
  JOIN [ItemCategory] ic0			ON it0.ItemID = ic0.ItemID 
  JOIN [CompoundItemContext] cic0	ON it0.ItemID = cic0.ItemID 
  JOIN   ContextComposition cc		ON (cic0.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  ic0.EndReleaseID is NULL
  AND	 cic0.EndReleaseID   IS NULL
  AND    cic0.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	pc.EndReleaseID IS NOT NULL 
  )
  UNION
  (SELECT tv.TableVID, tv.Code as TableCode, 'Table_Context' as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   ContextComposition cc		ON (tv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND   mv.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	pc.EndReleaseID IS NOT NULL 
  )

  ) sq
  ORDER BY sq.TableVID;


-- 25c.	Property Code.EndReleaseID is NOTE NULLin a context
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
		 '4_7c'																									AS ViolationCode, 
		 left('Property Code ('+ sq.PropertyCategoryCode + ') has Expired',255) AS Violation,
		 1																										AS isBlocking,
		 sq.TableVID																							AS TableVID, 
		 NULL																									AS OldTableVID,
		 left(trim(sq.TableCode),40)																			AS TableCode, 
		 NULL																									AS HeaderID, 
		 left(trim(sq.HeaderCode),30)																			AS HeaderCode, 
		 NULL																									AS HeaderVID, 
		 NULL																									AS OldHeaderVID, 
		 NULL																									AS KeyHeader, 
		 NULL																									AS HeaderDirection, 
		 sq.PropertyID																									AS HeaderPropertyID, 
		 sq.PropertyCode																						AS HeaderPropertyCode, 
		 NULL																									AS HeaderSubcategoryID, 
		 NULL																									AS HeaderSubcategoryName, 
		 NULL																									AS HeaderContextID, 
  	     NULL       																							AS CategoryID, 
  	     NULL																									AS CategoryCode, 
		 NULL																									AS ItemID,
		 NULL																									AS ItemCode,
		 NULL																									AS CellID,
		 NULL																									AS CellCode,
		 NULL																									AS Ceell2ID,
		 NULL																									AS Cell2Code,
		 NULL																									AS VVEndReleaseID,
		 NULL																									AS NewAspect
  FROM
  (
  (SELECT tv.TableVID, tv.Code as TableCode, h.Direction+'_'+hv.Code as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]			h		ON (h.TableID		= t.TableID)
  JOIN   HeaderVersion		hv		ON (hv.HeaderID		= h.HeaderID)
  JOIN   TableVersionHeader tvh		ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   ContextComposition cc		ON (hv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID) 
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  JOIN	 Release rpi				ON rpi.ReleaseID	= itc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		   = 0
  AND	 tvh.isAbstract    = 0 
  AND rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND rpi.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN ItemCategory icp3 ON r3.ReleaseID=icp3.StartReleaseID WHERE icp3.ItemID = cc.PropertyID) 
  AND ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND itc.EndReleaseID IS NOT NULL 
  )
  UNION
  (SELECT 0, 'CompoundItemID: '+cast(it0.ItemID as nvarchar)+'  CompoundItemCode: '+left(ic0.Code,13) as TableCode, NULL as HeaderCode, 
  cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   Item it0 
  JOIN [ItemCategory] ic0			ON it0.ItemID = ic0.ItemID 
  JOIN [CompoundItemContext] cic0	ON it0.ItemID = cic0.ItemID 
  JOIN   ContextComposition cc		ON (cic0.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  JOIN	 Release rpi				ON rpi.ReleaseID	= itc.StartReleaseID 
  WHERE  ic0.EndReleaseID is NULL
  AND	 cic0.EndReleaseID   IS NULL
  AND    cic0.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 rpi.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN ItemCategory icp3 ON r3.ReleaseID=icp3.StartReleaseID WHERE icp3.ItemID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	 itc.EndReleaseID IS NOT NULL 
  )
  UNION
  (SELECT tv.TableVID, tv.Code as TableCode, 'Table_Context' as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   ContextComposition cc		ON (tv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  JOIN	 Release rpi				ON rpi.ReleaseID	= itc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND   mv.StartReleaseID = @CurrentRelease 
  AND	rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	rpi.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN ItemCategory icp3 ON r3.ReleaseID=icp3.StartReleaseID WHERE icp3.ItemID = cc.PropertyID) 
  AND	ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	itc.EndReleaseID IS NOT NULL 
  )

  ) sq
  ORDER BY sq.TableVID;


-- 25d.	ItemCategory.EndReleaseID is NOT NULL in a context
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
		 '4_7d'																									AS ViolationCode, 
		 left('Item Category (' +sq.ItemCategoryCode + ') has Expired',255) AS Violation,
		 1																										AS isBlocking,
		 sq.TableVID																							AS TableVID, 
		 NULL																									AS OldTableVID,
		 left(trim(sq.TableCode),40)																			AS TableCode, 
		 NULL																									AS HeaderID, 
		 left(trim(sq.HeaderCode),30)																			AS HeaderCode, 
		 NULL																									AS HeaderVID, 
		 NULL																									AS OldHeaderVID, 
		 NULL																									AS KeyHeader, 
		 NULL																									AS HeaderDirection, 
		 NULL																									AS HeaderPropertyID, 
		 NULL																						AS HeaderPropertyCode, 
		 NULL																									AS HeaderSubcategoryID, 
		 NULL																									AS HeaderSubcategoryName, 
		 NULL																									AS HeaderContextID, 
  	     NULL       																							AS CategoryID, 
  	     NULL																									AS CategoryCode, 
		 sq.ItemID																								AS ItemID,
		 sq.ItemCode																							AS ItemCode,
		 NULL																									AS CellID,
		 NULL																									AS CellCode,
		 NULL																									AS Ceell2ID,
		 NULL																									AS Cell2Code,
		 NULL																									AS VVEndReleaseID,
		 NULL																									AS NewAspect
  FROM
  (
  (SELECT tv.TableVID, tv.Code as TableCode, h.Direction+'_'+hv.Code as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]			h		ON (h.TableID		= t.TableID)
  JOIN   HeaderVersion		hv		ON (hv.HeaderID		= h.HeaderID)
  JOIN   TableVersionHeader tvh		ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   ContextComposition cc		ON (hv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID) 
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		   = 0
  AND	 tvh.isAbstract    = 0 
  AND rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	itc2.EndReleaseID IS NOT NULL 
  )
  UNION
  (SELECT 0, 'CompoundItemID: '+cast(it0.ItemID as nvarchar)+'  CompoundItemCode: '+left(ic0.Code,13) as TableCode, NULL as HeaderCode, 
  cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   Item it0 
  JOIN [ItemCategory] ic0			ON it0.ItemID = ic0.ItemID 
  JOIN [CompoundItemContext] cic0	ON it0.ItemID = cic0.ItemID 
  JOIN   ContextComposition cc		ON (cic0.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  ic0.EndReleaseID is NULL
  AND	 cic0.EndReleaseID   IS NULL
  AND    cic0.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	itc2.EndReleaseID IS NOT NULL 
  )
  UNION
  (SELECT tv.TableVID, tv.Code as TableCode, 'Table_Context' as HeaderCode, cc.PropertyID as PropertyID, itc.Code as PropertyCode, itc2.ItemID, itc2.Code as ItemCode, c.Code as PropertyCategoryCode, c2.Code as ItemCategoryCode  
  FROM   TableVersion		tv 
  JOIN   [Table]			t		ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   ContextComposition cc		ON (tv.ContextID	= cc.ContextID) 
  JOIN   ItemCategory		itc		ON (itc.ItemID		= cc.PropertyID)
  JOIN   PropertyCategory	pc		ON (cc.PropertyID	= pc.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 
  JOIN   ItemCategory		itc2	ON (itc2.ItemID		= cc.ItemID)
  JOIN   Category			c2		ON (itc2.CategoryID	= c2.CategoryID)
  JOIN	 Release ri					ON ri.ReleaseID		= itc2.StartReleaseID 
  JOIN	 Release rp					ON rp.ReleaseID		= pc.StartReleaseID 
  WHERE  t.IsAbstract	   = 0
  AND	 tv.EndReleaseID   IS NULL
  AND   mv.StartReleaseID = @CurrentRelease 
  AND	 rp.Date in (SELECT max(r3.Date) FROM Release r3 INNER JOIN PropertyCategory pc3 ON r3.ReleaseID=pc3.StartReleaseID WHERE pc3.PropertyID = cc.PropertyID) 
  AND	 ri.Date in (SELECT max(r4.Date) FROM Release r4 INNER JOIN ItemCategory ic4 ON r4.ReleaseID=ic4.StartReleaseID WHERE ic4.ItemID = cc.ItemID)
  AND	itc2.EndReleaseID IS NOT NULL 
  )

  ) sq
  ORDER BY sq.TableVID;





-- 26: For All non-key Headers of all TableVersions with StartRelease=CurrentRelease each PropertyID that is assigned to a SubCategoryVID must be assigned to a Unique SubCategoryVID 
--     AND also this SubCategoryVID has to have EndReleaseID=Null

  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 2
  SELECT DISTINCT 
		 '4_8'																										AS ViolationCode, 
		 'Main Property on ModuleVesions of this Release has been assigned to more than one distinct SubCategories' AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 NULL																										AS HeaderID, 
		 hv.Code																									AS HeaderCode, 
		 hv.HeaderVId																								AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 h.isKey																									AS KeyHeader, 
		 h.Direction																								AS HeaderDirection, 
		 hv.PropertyID																								AS HeaderPropertyID, 
		 itc.Code																									AS HeaderPropertyCode, 
		 sc.SubCategoryID   																						AS HeaderSubcategoryID, 
		 left(sc.[Name],60)																							AS HeaderSubcategoryName,		 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID       																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			tv 
  JOIN   [Table] 					t 	ON (t.TableID			= tv.TableID) 
  JOIN   [Header] 					h 	ON (t.TableID			= h.TableID) 
  JOIN   [HeaderVersion] 			hv 	ON (h.HeaderID			= hv.HeaderID)
  JOIN   [TableVersionHeader] 		tvh ON (
  											tv.TableVID			= tvh.TableVID 
  										  AND 
  										    tvh.HeaderID		= h.HeaderID
  										   )
  JOIN   [SubCategoryVersion] 		scv ON (scv.SubCategoryVID	= hv.SubCategoryVID) 
  JOIN   [SubCategory] 				sc 	ON (sc.SubCategoryID	= scv.SubCategoryID) 
  JOIN   [Category]					c   ON (c.CategoryID	    = sc.CategoryID) 
  JOIN   [ItemCategory] 			itc ON (itc.ItemID			= hv.PropertyID) 
  JOIN   [Item] 					it 	ON (itc.ItemID			= it.ItemID)
  JOIN   [ModuleVersionComposition] mvc ON (tv.TableVID			= mvc.TableVID)
  JOIN   [ModuleVersion] 			mv 	ON (mv.ModuleVID		= mvc.ModuleVID)
  WHERE  mv.StartReleaseID = @CurrentRelease 
  --AND	 tv.StartReleaseID = @CurrentRelease 
  AND    h.isKey			  = 0 
  AND    tvh.isAbstract	  = 0 
  AND    hv.PropertyID IS NOT NULL 
  AND    hv.SubCategoryVID IS NOT NULL 
  AND    scv.EndReleaseID is Null
  AND    1 < (SELECT COUNT(DISTINCT hv2.SubCategoryVID)  
              FROM	 [HeaderVersion]				hv2 
  			  JOIN	 [TableVersionHeader]			tvh2 ON (tvh2.HeaderVID = hv2.HeaderVID)
  			  JOIN	 [Header]						h2	 ON (hv2.HeaderID	= h2.HeaderID)
  			  JOIN	 [ModuleVersionComposition] 	mvc2 ON (tvh2.TableVID	= mvc2.TableVID)
              JOIN	 [ModuleVersion]				mv2  ON (mv2.ModuleVID	= mvc2.ModuleVID)
  			  WHERE  h2.isKey			= 0 
  			  AND	 tvh2.IsAbstract	= 0 
  			  AND	 mv2.StartReleaseID = mv.StartReleaseID 
  			  AND	 hv2.PropertyID		IS NOT NULL 
  			  AND	 hv2.SubCategoryVID IS NOT NULL 
  			  AND	 hv2.PropertyID		= hv.PropertyID 
             ) 
  




  -- 30 For every Non-Abstract Table in ModuleVersionComposiiton, for which : TableVersion.AbstractTableID is not null, 
  --    the corresponding pair of (ModuuleVID, TableID=TableVersion.AbstractTableID) must also be present in ModuleVersionComposition
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '1_3'																										AS ViolationCode, 
		 'A TableVersion that is related to a non-Null AbstractTableID is present in ModuleVersionComposition but its AbstractTableID is not present in ModuleVersionComposiiton fo rthe same ModuleVID' AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 NULL																										AS HeaderID, 
		 left('MVCode='+mv.Code,30)																					AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Table] t
  JOIN	 [TableVersion] 			tv  ON (t.TableID			= tv.TableID) 
  JOIN   [ModuleVersionComposition]	mvc	ON (tv.TableVID			= mvc.TableVID) 
  JOIN	 [ModuleVersion]			mv  ON (mv.ModuleVID		= mvc.ModuleVID) 
  WHERE  mv.StartReleaseID = @CurrentRelease 
  AND    t.IsAbstract	  = 0 
  AND    tv.AbstractTableID is not Null
  AND    tv.AbstractTableID NOT IN
			 (SELECT mvc2.TableID
              FROM	 [ModuleVersionComposition] 	mvc2
  			  WHERE  mvc2.ModuleVID = mvc.ModuleVID
             ) 


  -- 31 For every Abstract Table in ModuleVersionComposiiton, 
  --    for the same ModuleVID there must exist a recowhere ModuleVersionComposition.TableVID.AbstractTableID = the target AbstractTableID
  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '1_4'																										AS ViolationCode, 
		 'An Abstract Table exists in ModuleVersionComposition without any non-Abstract Table corresponding to the same ModuleVersion' AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 NULL																										AS HeaderID, 
		 left('MVCode='+mv.Code,30)																					AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Table] t
  JOIN	 [TableVersion] 			tv  ON (t.TableID			= tv.TableID) 
  JOIN   [ModuleVersionComposition]	mvc	ON (tv.TableVID			= mvc.TableVID) 
  JOIN	 [ModuleVersion]			mv  ON (mv.ModuleVID		= mvc.ModuleVID) 
  WHERE  mv.StartReleaseID = @CurrentRelease 
  AND    t.IsAbstract	  = 1 
  AND    t.TableID NOT IN
			 (SELECT tv2.AbstractTableID
              FROM	 [TableVersion]                 tv2
			  JOIN [Table]                          t2   on (tv2.TableID=t2.TableID)
			  JOIN   [ModuleVersionComposition] 	mvc2 on (mvc2.TableVID = tv2.TableVID)
  			  WHERE  mvc2.ModuleVID = mvc.ModuleVID
  			  AND	 t2.IsAbstract	= 0 
             ) 



-- 32 Same TableVersion Code must always belong to one TableID
  INSERT INTO ModelViolations 
  -- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '1_5'																										AS ViolationCode, 
		 'Duplicate Table Code' AS Violation,
		 0																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code			    																					AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			tv 
   JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
   JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  WHERE  tv.EndReleaseID is Null 
  AND   tv.StartReleaseID = @CurrentRelease
  and   tv.TableVID in (SELECT mvc1.TableVID  
                        FROM ModuleVersionComposition mvc1 
 						INNER JOIN ModuleVersion mv1 ON mvc1.ModuleVID=mv1.ModuleVID 
 						WHERE mv1.EndReleaseID is Null
                        )  
  AND    trim(tv.Code) IN
			 (SELECT trim(tv2.Code)
              FROM	 [TableVersion]                 tv2
			  INNER JOIN ModuleVersionComposition mvc2 ON tv2.TableVID=mvc2.TableVID 
			  INNER JOIN ModuleVersion mv2 ON mv2.ModuleVID = mvc2.ModuleVID 
  			  WHERE  (tv2.TableID <> tv.TableID) AND (tv2.EndReleaseID is NULL)
  			  AND	 mv2.EndReleaseID	is NULL 
             ) 




  -- 35 Every TableGroup is not recommended to contain Abstract Tables in its TableGroupComposition
  
  INSERT INTO ModelViolations 
  -- DECLARE @CurrentRelease int = 2
  SELECT DISTINCT 
		 '1_6'																										AS ViolationCode, 
		 'Warning: Abstract Table found in Composiiton of TableGroup'												AS Violation,
		 0																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code			    																					AS TableCode, 
		 tg.TableGroupID																							AS HeaderID, 
		 left('TableGroup: ' + tg.Code, 30)																            AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			 tv 
  INNER JOIN [Table]                 t   ON tv.TableID=t.TableID 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  INNER JOIN [TableGroupComposition] tgc ON tgc.TableID=t.TableID 
  INNER JOIN [TableGroup]            tg  ON tgc.TableGroupID=tg.TableGroupID 
  WHERE tv.EndReleaseID is Null 
  AND   tgc.StartReleaseID = @CurrentRelease
  AND   tgc.EndReleaseID is NULL
  AND   t.IsAbstract = 1              



  -- 36 For every Property employed by any Object defined in this CurrentRelease there has to exist one and only one PropertyCategory with EndRelease=Null
  
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3
    SELECT DISTINCT 
		 '6_1'																										AS ViolationCode, 
		 'Property employed in CurrentRelease has not Unique PropertyCategory with EndRelease=Null '				AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Property] p 
  WHERE 
  1<>(select count(pc.StartReleaseID) from PropertyCategory pc where p.PropertyID=pc.PropertyID and pc.EndReleaseID is Null)
AND
(
(p.PropertyID in (select cc.PropertyID from contextcomposition cc inner join headerversion hv on cc.ContextID=hv.ContextID where hv.StartReleaseID= @CurrentRelease) ) OR 
(p.PropertyID in (select cc.PropertyID from contextcomposition cc inner join tableversion tv on cc.ContextID=tv.ContextID where tv.StartReleaseID= @CurrentRelease) ) OR 
(p.PropertyID in (select hv.PropertyID from Headerversion hv where hv.StartReleaseID= @CurrentRelease) ) OR 
(p.PropertyID in (select tv.PropertyID from Tableversion tv where tv.StartReleaseID= @CurrentRelease) ) 
)



  -- 37 For every Item employed by any Object defined in this CurrentRelease there has to exist one and only one ItemCategory with EndRelease=Null
  
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_2'																										AS ViolationCode, 
		 'Item employed in CurrentRelease has not Unique ItemCategory with EndRelease=Null '						AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 it.ItemID																									AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Item] it 
  WHERE 
  1<>(select count(ic.StartReleaseID) from ItemCategory ic where it.ItemID=ic.ItemID and ic.EndReleaseID is Null)
AND
(
(it.ItemID in (select cc.ItemID from contextcomposition cc inner join headerversion hv on cc.ContextID=hv.ContextID where hv.StartReleaseID= @CurrentRelease) ) OR 
(it.ItemID in (select cc.ItemID from contextcomposition cc inner join tableversion tv on cc.ContextID=tv.ContextID where tv.StartReleaseID= @CurrentRelease) ) OR 
(it.ItemID in (select cc.ItemID from contextcomposition cc inner join variableversion vv on cc.ContextID=vv.ContextID where vv.StartReleaseID= @CurrentRelease) ) OR 
(it.ItemID in (select PropertyID from Property) ) OR 
(it.ItemID in (select cic.ItemID from CompoundItemContext cic where cic.StartReleaseID= @CurrentRelease) ) OR 
(it.ItemID in (select sci.ItemID from SubCategoryItem sci INNER JOIN SubCategoryVersion scv ON sci.SubCategoryVID=scv.SubCategoryVID where scv.StartReleaseID= @CurrentRelease) ) 
)


-- 38: For  Every TableVersionHeader that has a Parent, its ParentHeader must also be as TableVersionHeader of the same TableVersion.
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 4
  SELECT DISTINCT 
		 '3_5'													AS ViolationCode, 
		 'Header whose Parent header does not belong to a TableVerswionHeader of the same TableVID'	AS Violation,
		 1														AS isBlocking,
		 tv.TableVID											AS TableVID, 
		 NULL													AS OldTableVID,
		 tv.Code												AS TableCode, 
		 h.HeaderID												AS HeaderID, 
		 hv.Code												AS HeaderCode, 
		 NULL													AS HeaderVID, 
		 NULL													AS OldHeaderVID, 
		 NULL													AS KeyHeader, 
		 h.Direction											AS HeaderDirection, 
		 NULL													AS HeaderPropertyID, 
		 NULL													AS HeaderPropertyCode, 
		 NULL													AS HeaderSubcategoryID, 
		 NULL													AS HeaderSubcategoryName, 
		 NULL													AS HeaderContextID, 
  	     NULL       											AS CategoryID, 
  	     NULL													AS CategoryCode, 
		 NULL													AS ItemID,
		 NULL													AS ItemCode,
		 NULL													AS CellID,
		 NULL													AS CellCode,
		 NULL													AS Ceell2ID,
		 NULL													AS Cell2Code,
		 NULL													AS VVEndReleaseID,
		 NULL													AS NewAspect
  FROM   [TableVersion]				tv 
  JOIN   [Table]					t	ON (t.TableID			= tv.TableID) 
  JOIN   [Header]					h	ON (h.TableID			= t.TableID)
  JOIN   [HeaderVersion]			hv	ON (hv.HeaderID			= h.HeaderId)
  JOIN   [TableVersionHeader]		tvh ON (
											tvh.HeaderVID		= hv.HeaderVId 
										  AND 
										    tvh.TableVID		= tv.TableVID
										   )
  JOIN   [ModuleVersionComposition]	mvc ON (tv.TableVID			= mvc.TableVID) 
  JOIN   [ModuleVersion]			mv	ON (mv.ModuleVID		= mvc.ModuleVID)
  WHERE  tv.EndReleaseID	IS NULL
  AND    mv.StartReleaseID	= @CurrentRelease 
  AND    tvh.ParentHeaderID	IS NOT NULL 
  AND	 tvh.ParentHeaderID	NOT IN (select tvh2.HeaderID from TableVersionHeader tvh2 where tvh2.TableVID=tvh.TableVID)
  ORDER BY tv.TableVID, 
		   h.Direction, 
		   h.HeaderID;



  -- 39 A Property can be a Metric if it belongs to a Compatible Data Type
  
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_3'																										AS ViolationCode, 
		 'Property is Metric but it belongs to incompatible DataType'												AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID       																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Property] p 
  INNER JOIN ItemCategory ic ON ic.ItemID=p.PropertyID
  INNER JOIN PropertyCategory pc ON pc.PropertyID=p.PropertyID 
  INNER JOIN Category c ON c.CategoryID=pc.CategoryID
  WHERE ic.EndReleaseID is Null 
  AND p.IsMetric = 1 
  AND p.DataTypeID not in (1,2,9,10)



-- 40: Property has to be a Metric if it belongs to monetary Data Type (DatatypeID=9)
  
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_4'																										AS ViolationCode, 
		 'Property is not Metric although it belongs to Monetary DataType'											AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID  																								AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Property] p 
  JOIN   ItemCategory ic ON ic.ItemID=p.PropertyID 
  JOIN   PropertyCategory	pc		ON (pc.PropertyID	= p.PropertyID) 
  JOIN   Category			c		ON (pc.CategoryID	= c.CategoryID) 

  WHERE ic.EndReleaseID is Null 
  AND p.IsMetric = 0 
  AND p.DataTypeID in (9) 
  AND pc.EndReleaseID is NULL



-- 41: A non-Enumrated Category (except 'Not applicable') cannot have associated Items or SubCategories
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_5'																										AS ViolationCode, 
		 'Non-Enumerated Category (other than Not applicable) with associated Items or SubCategories'				AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID       																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Category] c 
  WHERE 
  (trim(c.Name)<>'Not applicable' ) AND 
  c.IsEnumerated<>1 AND  
  ( (c.CategoryID in (select ic.CategoryID from ItemCategory ic)) OR  
  (c.CategoryID in (select sc.CategoryID from SubCategory sc))  ) 




  -- 42 An ItemCode (including Property) has to be Unique within its associated Category amongst all ItemCategory assignments with EndRelease=Null
  -- a.ItemCode
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_6'																										AS ViolationCode, 
		 'Duplicate ItemCode within a specific Category amongst Active Items (with EndRelease=Null)'				AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID  																								AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 it.ItemID																									AS ItemID,
		 ic.Code																									AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Item] it 
  INNER JOIN ItemCategory ic on ic.ItemID=it.ItemID 
  INNER JOIN Category c ON c.CategoryID=ic.CategoryID
  WHERE 
  it.IsProperty=0 AND
  ic.EndReleaseID is Null AND 
  (1<>(select count(distinct ic2.ItemID) from ItemCategory ic2 where ic2.Code=ic.Code and ic2.CategoryID=ic.CategoryID and ic2.EndReleaseID is Null))


  -- 42 An ItemCode (including Property) has to be Unique within its associated Category amongst all ItemCategory assignments with EndRelease=Null
  -- b.PropertyCode
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_6'																										AS ViolationCode, 
		 'Duplicate PropertyCode within a specific Category amongst Active Items (with EndRelease=Null)'			AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID  																								AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 it.ItemID																									AS ItemID,
		 ic.Code																									AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Item] it 
  INNER JOIN ItemCategory ic on ic.ItemID=it.ItemID 
  INNER JOIN PropertyCategory pc ON pc.PropertyID=it.ItemID 
  INNER JOIN Category c ON c.CategoryID=pc.CategoryID
  WHERE 
  it.IsProperty=1 AND
  pc.EndReleaseID is Null AND 
  ic.EndReleaseID is Null AND 
  (1<>(select count(distinct ic2.ItemID) from ItemCategory ic2 inner join PropertyCategory pc2 on ic2.ItemID=pc2.PropertyID where ic2.Code=ic.Code and ic2.EndReleaseID is Null and pc2.EndReleaseID is Null))



-- 43: A Metric can never belong to an Enumerated Property Category

  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_7'																										AS ViolationCode, 
		 'A Property that is Metric belongs to an Enumerated (Property) Category'									AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID       																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Category] c 
  INNER JOIN PropertyCategory pc on pc.CategoryID=c.CategoryID 
  INNER JOIN Property p ON p.PropertyID=pc.PropertyID 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  WHERE 
  p.IsMetric = 1 AND 
  c.IsEnumerated=1 AND  
  pc.EndReleaseID is Null AND 
  ic.EndReleaseID is Null


-- 44:  For All active ModuleVersions (with EndRelease=Null), the corresponding TableVersions in tableversioncomposition must also be Active 
--      (i.e must also have: TableVersion.EndRelease=Null)

  INSERT INTO ModelViolations 
  SELECT DISTINCT 
		 '1_7'																										AS ViolationCode, 
		 left('Expired TableVersion in an Active ModuleVersion with StartRelease='+r.Code+': One way to update is to create New ModuleVersion in this Release and update to latest active TableVersion',255) AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code			    																					AS TableCode, 
		 NULL																										AS HeaderID, 
		 'Module Code:'+left(mv.Code,18)																			AS HeaderCode,	
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			tv 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID 
  JOIN Release r on mv.StartReleaseID=r.ReleaseID 
  WHERE  tv.EndReleaseID is Not Null 
  AND    mv.EndReleaseID is Null
  


-- 45:  All New ModuleVersions (with StartRelease=CurrentRelease) should contain at least on Table in their ModuleVersionComposition

  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '1_8'																										AS ViolationCode, 
		 'New ModuleVersion without any Table included in their ModuleVersionComposition'							AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 'Module Code:'+left(mv.Code,18)																			AS HeaderCode,	
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [ModuleVersion] 			mv 
  INNER JOIN [Module] md ON mv.ModuleID=md.ModuleID 
  WHERE    mv.StartReleaseID = @CurrentRelease 
  AND md.isDocumentModule = 0
  AND      mv.ModuleVID not in (select ModuleVID from ModuleVersionComposition)



-- 46:  Every New ModuleVersions (with StartRelease=CurrentRelease) should contain at least one TableID or TableVID not existing in the ModuleVersionComposiiton of the previous ModuleVersion
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
		 '1_9'																										AS ViolationCode, 
		 'New ModuleVersion has exactly the same ModuleVersionComposition as the previous ModuleVersion'			AS Violation,
		 0																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 'Module Code:'+left(mv.Code,18)																			AS HeaderCode,	
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [ModuleVersion] 			mv 
  INNER JOIN [Module] md ON mv.ModuleID=md.ModuleID 
  WHERE    mv.StartReleaseID = @CurrentRelease 
  AND      md.isDocumentModule = 0 
  AND      not exists (select mvc.* from ModuleVersionComposition mvc 
					   where mvc.ModuleVID=mv.ModuleVID and 
						(mvc.tablevid not in (select mvc2.tablevid from moduleversioncomposition mvc2 inner join moduleversion mv2 on mvc2.modulevid=mv2.modulevid 
					     where mv2.moduleid=mv.moduleid and mv2.endreleaseid=@CurrentRelease)  	
						 )
					   )
  AND      not exists (select mvc2.* from ModuleVersionComposition mvc2 inner join moduleversion mv2 on mvc2.modulevid=mv2.modulevid 
					   where mv2.ModuleID=mv.ModuleID and 
					   mv2.EndReleaseID = @CurrentRelease and
						(mvc2.tablevid not in (select mvc.tablevid from moduleversioncomposition mvc 
					    where mvc.modulevid=mv.modulevid)  	
						)
					   )
  AND			exists (SELECT mv2.ModuleVID from MODULEvERSION MV2 where mv2.ModuleID=mv.ModuleID AND mv2.ModuleVID<>mv.ModuleVID )		    


-- 47  If on a Cell  a corresponding HeaderVersion has Main PropertyID that is not a Metric then we are not allowed to set any Sign on this Cell	
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode)
-- DECLARE @CurrentRelease int = 2 --1020000001 
  SELECT DISTINCT 
  '6_8' as ViolationCode, 
  'On this Cell there was set a Sign whilst the crresponding Main Property is non-Metric.' AS Violation,
  1 as isBlocking,
  tv.TableVID as TableVID, 
  tv.Code as TableCode, 
  tvc.CellID as CellID, 
  tvc.CellCode  as CellCode 
  FROM   TableVersionCell tvc 
  JOIN   TableVersion     tv  ON (tv.TableVID   = tvc.TableVID) 
  WHERE  tvc.IsVoid  	      = 0 
  AND tvc.[Sign] is not null 
  AND tvc.Sign<>''
  AND    tv.StartReleaseID=@CurrentRelease
  AND	 exists (select p.PropertyID 
				 FROM Property p
				 WHERE p.IsMetric=0 
				 AND p.PropertyID in (select hv.PropertyID 
									  FROM HeaderVersion hv 
									  INNER JOIN TableVersionHeader tvh on hv.HeaderVID=tvh.HeaderVID 
									  INNER JOIN Header h on h.HeaderID=hv.HeaderID
									  INNER JOIN Cell cl on (cl.ColumnID=h.HeaderID or cl.RowID=h.HeaderID or cl.SheetID=h.HeaderID) 
									  WHERE tvh.TableVID=tv.TableVID
									  AND tvc.CellID=cl.CellID 
									  AND hv.PropertyID is Not Null
									 )
				)
  ORDER BY tv.TableVID, 
		   tvc.CellCode;



-- 48: Every TableGroup is not recommended to contain in its TableGroupComposition any Table that does not belong to any ModuleVersionComposition
  INSERT INTO ModelViolations 
  -- DECLARE @CurrentRelease int = 2
  SELECT DISTINCT 
		 '1_10'																										AS ViolationCode, 
		 'Table without any assignment to any Module, is found in the composition of a TableGroup'					AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code			    																					AS TableCode, 
		 tg.TableGroupID																							AS HeaderID, 
		 left('TableGroup:' + trim(tg.Code),30)															            AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			 tv 
  INNER JOIN [Table]                 t   ON tv.TableID=t.TableID 
  INNER JOIN [TableGroupComposition] tgc ON tgc.TableID=t.TableID 
  INNER JOIN [TableGroup]            tg  ON tgc.TableGroupID=tg.TableGroupID 
  WHERE tv.EndReleaseID is Null 
  AND   tgc.StartReleaseID = @CurrentRelease
  AND   tgc.EndReleaseID is NULL
  AND   t.TableID not in (select mvc.TableID from ModuleVersionComposition mvc 
						  INNER JOIN ModuleVersion mv on mv.ModuleVID=mvc.ModuleVID 
   					      WHERE mv.EndReleaseID is Null
						 )
						   

-- 49: An Enumrated Category must have one Default Item associated with it
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_9'																										AS ViolationCode, 
		 'Enumerated Category has not default item associated with it'												AS Violation,
		 0																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID       																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Category] c 
  WHERE 
  c.IsEnumerated=1 AND (c.Code not in ('_PR', '_TE')  ) AND 
  (not exists (SELECT ic.* from ItemCategory ic where ic.CategoryID=c.CategoryID and ic.StartReleaseID<>@CurrentRelease)) AND 
  (not exists (SELECT scv.* from SubCategoryVersion scv inner join SubCategory sc on sc.SubCategoryID=scv.SubCategoryID where sc.CategoryID=c.CategoryID and scv.StartReleaseID<>@CurrentRelease)) AND 
  ( (0 in (select count(distinct ic.ItemID) from ItemCategory ic where ic.CategoryID=c.CategoryID and ic.EndReleaseID is null and ic.IsDefaultItem=1))  ) 



-- 50: An Enumrated Category must have ONLY ONE Default Item associated with it
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_10'																										AS ViolationCode, 
		 'Enumerated Category has MORE THAN ONE default items associated with it'									AS Violation,
		 1																											AS isBlocking,
		 NULL   																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL			    																						AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID       																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [Category] c 
  WHERE 
  c.IsEnumerated=1 AND (c.Code not in ('_PR', '_TE')  ) AND 
  ( (1 < (select count(distinct ic.ItemID) from ItemCategory ic where ic.CategoryID=c.CategoryID and ic.EndReleaseID is null and ic.IsDefaultItem=1))  ) 




-- 51: A Code cannot contain spaces in-between
-- 51_1: Framework
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'FRAMEWORK Code with Spaces in between									'									AS Violation,
		 1																											AS isBlocking,
		 f.FrameworkID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 f.Code + ' (FRAMEWORK)'																					AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Framework f  
  WHERE 
  charindex(' ',trim(f.Code))>0 AND 
  not exists (SELECT mv.* FROM ModuleVersion mv inner join Module m on mv.ModuleID=m.moduleID 
			  WHERE m.FrameworkID=f.FrameworkID and mv.StartReleaseID<>@CurrentRelease) AND 
  exists     (SELECT m.* FROM Module m WHERE m.FrameworkID=f.FrameworkID)



-- 51: A Code cannot contain spaces in-between
-- 51_2: Module(Version)
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'MODULE Code with Spaces in between									'									AS Violation,
		 1																											AS isBlocking,
		 mv.ModuleVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(mv.Code + ' (MODULE)',40)																				AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   ModuleVersion mv    
  WHERE   charindex(' ',trim(mv.Code))>0 AND  mv.StartReleaseID=@CurrentRelease 




-- 51: A Code cannot contain spaces in-between
-- 51_3: Table(Version)
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'TABLE Code with Spaces in between										'									AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(tv.Code + ' (TABLE)',40)																				AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   TableVersion tv    
  WHERE   charindex(' ',trim(tv.Code))>0 AND  tv.StartReleaseID=@CurrentRelease 


  
-- 51: A Code cannot contain spaces in-between
-- 51_4: TableGroup
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 1
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'TABLEGROUP Code with Spaces in between								'									AS Violation,
		 0																											AS isBlocking,
		 tg.TableGroupID																							AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(trim(tg.Code) + ' (TABLEGROUP)',40)																	AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   TableGroup tg    
  WHERE   charindex(' ',trim(tg.Code))>0 AND  tg.StartReleaseID=@CurrentRelease 


  
-- 51: A Code cannot contain spaces in-between
-- 51_5: Header(Version)
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'HEADER Code with Spaces in between									'									AS Violation,
		 1																											AS isBlocking,
		 hv.HeaderVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(hv.Code + ' (HEADER)',40)																				AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   HeaderVersion hv    
  WHERE   hv.Code is not Null and charindex(' ',trim(hv.Code))>0 AND  hv.StartReleaseID=@CurrentRelease 


  
  
-- 51: A Code cannot contain spaces in-between
-- 51_6: Variable(Version)
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'VARIABLE Code with Spaces in between									'									AS Violation,
		 1																											AS isBlocking,
		 vv.VariableVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(vv.Code + ' (VARIABLE)',40)																			AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   VariableVersion vv    
  WHERE   vv.Code is not Null AND charindex(' ',trim(vv.Code))>0 AND  vv.StartReleaseID=@CurrentRelease 


  
-- 51: A Code cannot contain spaces in-between
-- 51_7: Item
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'ITEM Code with Spaces in between										'									AS Violation,
		 1																											AS isBlocking,
		 ic.ItemID																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(ic.Code + ' (ITEM from Category '+c.Code+')',40)														AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   ItemCategory ic INNER JOIN Item it on ic.ItemID=it.ItemID  inner join Category c on c.CategoryID=ic.CategoryID 
  WHERE   ic.Code is not Null AND charindex(' ',trim(ic.Code))>0 AND  ic.StartReleaseID=@CurrentRelease AND it.IsProperty=0 AND ic.EndReleaseID is NULL


  
  
-- 51: A Code cannot contain spaces in-between
-- 51_8: Property
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'PROPERTY Code with Spaces in between									'									AS Violation,
		 1																											AS isBlocking,
		 ic.ItemID																									AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(ic.Code + ' (PROPERTY)',40)																			AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   ItemCategory ic 
  INNER JOIN Item it on ic.ItemID=it.ItemID 
  INNER JOIN PropertyCategory pc on pc.PropertyID=it.ItemID 
  INNER JOIN Category c ON c.CategoryID=ic.CategoryID
  WHERE   ic.Code is not Null AND charindex(' ',trim(ic.Code))>0 AND  ic.StartReleaseID=@CurrentRelease AND it.IsProperty=1 
  AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL 


  -- 51: A Code cannot contain spaces in-between
-- 51_9: SubCategory
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'SUBCATEGORY Code with Spaces in between								'									AS Violation,
		 1																											AS isBlocking,
		 sc.SubCategoryID																							AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(trim(sc.Code) + ' (SUBCATEGORY from Category '+c.Code+')',40)											AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   SubCategory sc 
  INNER JOIN Category c on c.CategoryID=sc.CategoryID
  WHERE   sc.Code is not Null AND charindex(' ',trim(sc.Code))>0 AND 
  (NOT EXISTS (SELECT * FROM SubCategoryVersion scv WHERE scv.SubCategoryID=sc.SubCategoryID AND scv.StartReleaseID<>@CurrentRelease))


  
  -- 51: A Code cannot contain spaces in-between
-- 51_10: Category
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'CATEGORY Code with Spaces in between								'										AS Violation,
		 1																											AS isBlocking,
		 c.CategoryID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(c.Code + ' (CATEGORY)',40)																			AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Category c 
  WHERE   c.Code is not Null AND charindex(' ',trim(c.Code))>0 AND 
  (NOT EXISTS (SELECT * FROM SubCategoryVersion scv inner join Subcategory sc on scv.SubCategoryID=sc.SubCategoryID WHERE sc.CategoryID=c.CategoryID AND scv.StartReleaseID<>@CurrentRelease)) AND 
  (NOT EXISTS (SELECT * FROM SuperCategoryComposition scc WHERE (scc.CategoryID=c.CategoryID or scc.SuperCategoryID=c.CategoryID) AND scc.StartReleaseID<>@CurrentRelease)) AND 
  (NOT EXISTS (SELECT * FROM ItemCategory ic WHERE ic.CategoryID=c.CategoryID AND ic.StartReleaseID<>@CurrentRelease)) AND 
  (NOT EXISTS (SELECT * FROM PropertyCategory pc WHERE pc.CategoryID=c.CategoryID AND pc.StartReleaseID<>@CurrentRelease))



-- 51: A Code cannot contain spaces in-between
-- 51_11: Operation
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_11'																										AS ViolationCode, 
		 'OPERATION Code with Spaces in between									'									AS Violation,
		 1																											AS isBlocking,
		 op.OperationID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(op.Code + ' (OPERATION)',40)																			AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Operation op     
  WHERE   charindex(' ',trim(op.Code))>0 AND  
		 (NOT EXISTS (SELECT * FROM OperationVersion opv WHERE opv.OperationID=op.OperationID AND opv.StartReleaseID<>@CurrentRelease))


 
-- 52: A HeaderVersion Code is recomended to be Numeric

  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_12'																										AS ViolationCode, 
		 'HEADER Code that is Not Numeric'																			AS Violation,
		 0																											AS isBlocking,
		 tv.TableVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 h.HeaderID																									AS HeaderID, 
		 hv.Code																									AS HeaderCode, 
		 hv.HeaderVID																								AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 h.isKey																									AS KeyHeader, 
		 h.Direction																								AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   HeaderVersion hv 
  INNER JOIN Header h on h.HeaderID=hv.HeaderID 
  INNER JOIN TableVersionHeader tvh on tvh.HeaderVID=hv.HeaderVID 
  INNER JOIN TableVersion tv on tv.TableVID=tvh.TableVID 
  WHERE   hv.Code is not Null and isNumeric(hv.Code)=0 AND  hv.StartReleaseID=@CurrentRelease and tv.EndReleaseID is Null


  
-- 53: Each Table is recommended to belong to one TableGroup of type 'templateGroup'
  INSERT INTO ModelViolations 
  -- DECLARE @CurrentRelease int = 2
  SELECT DISTINCT 
		 '1_11'																										AS ViolationCode, 
		 'Table belongs to more than one TableGroups of type templateGroup						'					AS Violation,
		 0																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code			    																					AS TableCode, 
		 tg.TableGroupID																							AS HeaderID, 
		 left('TableGroup:' + trim(tg.Code),30)															            AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			 tv 
  INNER JOIN [Table]                 t   ON tv.TableID=t.TableID 
  INNER JOIN [TableGroupComposition] tgc ON tgc.TableID=t.TableID 
  INNER JOIN [TableGroup]            tg  ON tgc.TableGroupID=tg.TableGroupID 
  WHERE tv.EndReleaseID is Null 
  AND   tgc.StartReleaseID = @CurrentRelease
  AND   tgc.EndReleaseID is NULL
  AND   1 < (select count(distinct tgc2.TableGroupID) from TableGroupComposition tgc2 INNER JOIN tableGroup tg2 on tg2.TableGroupID=tgc2.TableGroupID  
						   WHERE tgc2.TableID=tgc.TableID and tg2.type='templateGroup' and tgc2.EndReleaseID is Null
						 )


-- SOS!!! LATER MAKE THIS RULE isBlocking=1
-- 54: All Tables belonging to the same TableGroup of type 'templateGroup' must be associated to the same Module in any active ModuleVersion
  INSERT INTO ModelViolations 
  -- DECLARE @CurrentRelease int = 2
  SELECT DISTINCT 
		 '1_12'																										AS ViolationCode, 
		 'TableGroup does not contain active Tables that all belong to at least one common Active ModuleVersion'		AS Violation,
		 1																											AS isBlocking,
		 NULL		   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL				    																					AS TableCode, 
		 tg.TableGroupID																							AS HeaderID, 
		 left('TableGroup:' + trim(tg.Code),30)															            AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableGroup]            tg 
  WHERE tg.EndReleaseID is Null 
  AND tg.type='templateGroup'
  AND NOT EXISTS (select mv.ModuleVID from ModuleVersion mv 
							WHERE  mv.EndReleaseID is NULL AND 
									(SELECT count(distinct tgc.TableID) FROM ModuleVersionComposition mvc 
										  INNER JOIN tableGroupComposition tgc on tgc.TableID=mvc.TableID  
										  INNER JOIN tableversion tv ON tgc.TableID=tv.TableID 
										  WHERE tgc.TableGroupID=tg.TableGroupID AND mv.ModuleVID=mvc.ModuleVID AND tgc.EndReleaseID is Null and tv.EndReleaseID is NULL
										  ) is NOT NULL AND  
								    (SELECT count(distinct tgc.TableID) FROM ModuleVersionComposition mvc 
										  INNER JOIN tableGroupComposition tgc on tgc.TableID=mvc.TableID  
										  INNER JOIN tableversion tv ON tgc.TableID=tv.TableID 
										  WHERE tgc.TableGroupID=tg.TableGroupID AND mv.ModuleVID=mvc.ModuleVID AND tgc.EndReleaseID is Null and tv.EndReleaseID is NULL
										  )
									= 
									(SELECT count(distinct tgc.TableID) FROM tableGroupComposition tgc 
										  INNER JOIN tableversion tv ON tgc.TableID=tv.TableID 
										  WHERE tgc.TableGroupID=tg.TableGroupID AND tgc.EndReleaseID is Null and tv.EndReleaseID is NULL
												)
						 )


-- SOS!!! LATER MAKE THIS RULE isBlocking=1
-- 55: Every active Table must belong to at least onee TableGroup of type 'templateGroup'
  INSERT INTO ModelViolations 
  -- DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
		 '1_13'																										AS ViolationCode, 
		 'Table does not belong to any TableGroup of type templateGroup							'					AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID   																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code			    																					AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																							            AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL       																								AS CategoryID, 
  	     NULL																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   [TableVersion] 			 tv 
  INNER JOIN [Table]                 t   ON tv.TableID=t.TableID 
  INNER JOIN moduleversioncomposition mvc0 ON mvc0.TableVID=tv.TableVID 
  INNER JOIN ModuleVersion mv0			   ON mvc0.ModuleVID=mv0.ModuleVID 
  WHERE tv.EndReleaseID is Null 
  AND t.IsAbstract = 0 
  AND mv0.StartReleaseID = @CurrentRelease 
  AND   NOT EXISTS (select * from TableGroupComposition tgc2 INNER JOIN tableGroup tg2 on tg2.TableGroupID=tgc2.TableGroupID  
						   WHERE tgc2.TableID=t.TableID and tg2.type='templateGroup' and tg2.EndReleaseID is Null  and tgc2.EndReleaseID is Null)
  AND EXISTS (select * FROM moduleversioncomposition mvc INNER JOIN ModuleVersion mv ON mvc.ModuleVID=mv.ModuleVID 
                            WHERE mvc.TableID=t.TableID and mv.EndReleaseID is Null)


  
   
-- 56: A Property belonging to an Enumerated Category has to have DataType='enumeration'; (DataTypeID=8)
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_13'																										AS ViolationCode, 
		 'Property belonging to an Enumerated Category whose Data Type is not enumeration'							AS Violation,
		 1																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  WHERE c.IsEnumerated=1 AND p.DataTypeID<>8 



-- 57: A Property belonging to a non-Enumerated Category (except _NA) must never have DtataType='enumeration; (DataTypeID=8) 
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_14'																										AS ViolationCode, 
		 'Property belonging to a non-enumerated Category (except _NA) whose Data Type is enumeration'				AS Violation,
		 1																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  WHERE c.IsEnumerated=0 AND p.DataTypeID=8 AND c.Code not in ('_NA')



-- 58. If a Property Code is Numeric after its first 2 characters, then this numeric part has to be unique amongst all existing Properties with the same feature
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_15'																										AS ViolationCode, 
		 'A Property code is numeric after its first 2 characters but the Numeric part (' + right(ic.Code,len(ic.Code)-2) + ') is not unique and is shared by other Properties also' AS Violation,
		 0																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  WHERE len(ic.Code)>2 and isnumeric(right(ic.Code,len(ic.Code)-2))=1 and
  exists (SELECT *  FROM   Property p2 
		  INNER JOIN ItemCategory ic2 ON p2.PropertyID=ic2.ItemID 
		  WHERE p2.PropertyID<>p.PropertyID and len(ic2.Code)>2 and 
		  isnumeric(right(ic2.Code,len(ic2.Code)-2))=1 and right(ic2.Code,len(ic2.Code)-2) = right(ic.Code,len(ic.Code)-2)
          )  
 ORDER by Violation



-- 59. A Property must always be associated with a DataType
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_16'																										AS ViolationCode, 
		 'A Property is not associated with any Data Type'															AS Violation,
		 1																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  WHERE p.DataTypeID is Null



-- 61: A Property belonging to an Enumerated Category is recommended to be associated with a SubCategory Lookup
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_18'																										AS ViolationCode, 
		 'Property belonging to an Enumerated Category but not associated with any SubCategory lookup'				AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID											AS TableVID, 
		 NULL													AS OldTableVID,
		 tv.Code												AS TableCode, 
		 h.HeaderID												AS HeaderID, 
		 hv.Code												AS HeaderCode, 
		 NULL													AS HeaderVID, 
		 NULL													AS OldHeaderVID, 
		 NULL													AS KeyHeader, 
		 h.Direction											AS HeaderDirection, 
		 p.PropertyID											AS HeaderPropertyID, 
		 ic.Code												AS HeaderPropertyCode, 
		 NULL													AS HeaderSubcategoryID, 
		 NULL													AS HeaderSubcategoryName, 
		 NULL													AS HeaderContextID, 
  	     c.CategoryID  											AS CategoryID, 
  	     c.Code													AS CategoryCode, 
		 NULL													AS ItemID,
		 NULL													AS ItemCode,
		 NULL													AS CellID,
		 NULL													AS CellCode,
		 NULL													AS Ceell2ID,
		 NULL													AS Cell2Code,
		 NULL													AS VVEndReleaseID,
		 NULL													AS NewAspect
  FROM   [TableVersion]				tv 
  JOIN   [Table]					t	ON (t.TableID			= tv.TableID) 
  JOIN   [Header]					h	ON (h.TableID			= t.TableID)
  JOIN   [HeaderVersion]			hv	ON (hv.HeaderID			= h.HeaderId)
  JOIN   [TableVersionHeader]		tvh ON (
											tvh.HeaderVID		= hv.HeaderVId 
										  AND 
										    tvh.TableVID		= tv.TableVID
										   )
  JOIN Property p ON p.PropertyID = hv.PropertyID
  JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  JOIN Category c ON pc.CategoryID=c.CategoryID
  WHERE  t.IsAbstract		= 0
  AND    tv.EndReleaseID	IS NULL
  AND    tv.StartReleaseID	= @CurrentRelease 
  AND    hv.SubCategoryVID	IS NULL
  AND	 c.isEnumerated = 1
  AND	 pc.EndReleaseID IS NULL
  AND	 ic.EndReleaseID IS NULL


-- 62: Each Header must have a non-null and non-blank Code
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_19'																										AS ViolationCode, 
		 'HEADER Code that is NULL or BLANK'																		AS Violation,
		 1																											AS isBlocking,
		 tv.TableVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 tv.Code																									AS TableCode, 
		 h.HeaderID																									AS HeaderID, 
		 hv.Code																									AS HeaderCode, 
		 hv.HeaderVID																								AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 h.isKey																									AS KeyHeader, 
		 h.Direction																								AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 'HEADER DESCR:' + left(hv.[Label],45)																		AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   HeaderVersion hv 
  INNER JOIN Header h on h.HeaderID=hv.HeaderID 
  INNER JOIN TableVersionHeader tvh on tvh.HeaderVID=hv.HeaderVID 
  INNER JOIN TableVersion tv on tv.TableVID=tvh.TableVID 
  WHERE   (hv.Code is Null OR trim(hv.Code)='') AND  hv.StartReleaseID=@CurrentRelease and tv.EndReleaseID is Null



-- 63. Each Module Version Number must be greater than the previous Module Version number
INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '1_14'																										AS ViolationCode, 
		 'MODULE Version Number that is not greater than the previous ModuleVerison number'							AS Violation,
		 1																											AS isBlocking,
		 mv.ModuleVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(mv.Code + ' (MODULE)',40)																				AS TableCode, 
		 NULL																										AS HeaderID, 
		 'Vers.Num:' + mv.VersionNumber																				AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   ModuleVersion mv    
  WHERE   mv.StartReleaseID=@CurrentRelease AND
  (mv.versionnumber is null OR
  exists (select mv2.* 
		  from moduleversion mv2 
		  where mv2.modulevid<>mv.modulevid 
		  and mv2.moduleid=mv.moduleid 
		  and mv2.VersionNumber is not null 
		  and mv2.VersionNumber >= mv.VersionNumber
		  )
  )

-- Create a temporary table #datatype_mapping to host all datatype mapping compatible with DP1.DataType table to facilitate taxonomy generation through DPM1
  DROP TABLE IF EXISTS #datatype_mapping
  SELECT * INTO #datatype_mapping from datatype
  UPDATE dt SET dt.code='d' FROM #datatype_mapping dt WHERE dt.code='dt'
  UPDATE dt SET dt.code='s' FROM #datatype_mapping dt WHERE dt.code='u'
  UPDATE dt SET dt.code='s' FROM #datatype_mapping dt WHERE dt.code='es'
  UPDATE dt SET dt.code='s' FROM #datatype_mapping dt WHERE dt.code='o'

   -- 64. If the user defines a PropertyCode with the first 2 letters to be corresponding to a DataType and FlowType prefix, 
 --     then the rest of the code has to be numeric. Moreover, the prefix has to coincide with the actual DataType and FlowType of this Property
 INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_20'																										AS ViolationCode, 
		 left('A Property Code has been defined with a datatype and flowtype prefix. However either the rest of the code is not numeric or this prefix does not match the Property DataType and FlowType',255)	AS Violation,
		 0																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 left('datatype:'+dt.code+' Flowtype:'+p.PeriodType,60)														AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  INNER JOIN #datatype_mapping dt on p.DataTypeID=dt.DataTypeID 
  WHERE  len(ic.Code)>2 
  AND (pc.StartReleaseID=@CurrentRelease OR ic.StartReleaseID=@CurrentRelease)
  AND left(trim(ic.Code),1) LIKE '[a-z]' COLLATE Latin1_General_100_BIN2 
  AND substring(trim(ic.Code),2,1) LIKE '[a-z]' COLLATE Latin1_General_100_BIN2 
  AND left(trim(ic.Code),1) in (select dt2.code from #datatype_mapping dt2) 
  AND substring(trim(ic.Code),2,1) in ('i','d') 
  AND 
  (isnumeric(right(trim(ic.Code),len(trim(ic.Code))-2))<>1 OR left(trim(ic.Code),1)<>dt.code OR substring(trim(ic.Code),2,1)<>(case when p.PeriodType='flow' then 'd' else 'i' end) )



-- 65. A Property Code cannot be a plain Numeric Code
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_21'																										AS ViolationCode, 
		 'A Property Code cannot be a plain Numeric Code'															AS Violation,
		 1																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  WHERE (ic.StartReleaseID=@CurrentRelease) and isnumeric(IC.Code)=1 
 

 
-- 66. A SubCategoryVersion created in this Current release should be examined for its retention if it is not employed by any HeaderVersion or VariableVersion
 INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_22'																										AS ViolationCode, 
		 'SubCategoryVersion created in this release is not used by any HeaderVersion or VariableVersion'			AS Violation,
		 0																											AS isBlocking,
		 sc.SubCategoryID																							AS TableVID, 
		 NULL																										AS OldTableVID,
		 left('SubCategory Code:'+trim(sc.Code),40)																	AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   SubCategory sc 
  INNER JOIN Category c on c.CategoryID=sc.CategoryID 
  inner join SubCategoryVersion SCV on SC.SubCategoryID=SCV.SubCategoryID 
  WHERE  
  scv.EndReleaseID is NULL and scv.StartReleaseID = @CurrentRelease 
  AND (NOT EXISTS (SELECT * FROM HeaderVersion hv WHERE hv.SubCategoryVID=scv.SubCategoryVID))
  AND (NOT EXISTS (SELECT * FROM VariableVersion vv WHERE vv.SubCategoryVID=scv.SubCategoryVID))


-- 67. All the Items of a SubCategory should Currently Belong either to the same Category as the whole SubCategory itself 
--     or (if the Category of SubCategory is a SuperCategory) to the constituent Categories of the SuperCategory itself.
 INSERT INTO ModelViolations 
 --DECLARE @CurrentRelease int = 3
    SELECT DISTINCT 
		 '6_23'																										AS ViolationCode, 
		 'There are Items of a SubCategory that do not Currently Belong to a Compatible Category with the Category of the SubCategory itself'	AS Violation,
		 1																											AS isBlocking,
		 sc.SubCategoryID																							AS TableVID, 
		 NULL																										AS OldTableVID,
		 left('SubCategory Code:'+trim(sc.Code),40)																	AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     left('CategOf: Subcat:'+c.Code+' Item:'+c2.Code,30)														AS CategoryCode, 
		 ic.ItemID																									AS ItemID,
		 ic.Code																									AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
FROM Category c 
INNER JOIN SubCategory sc ON sc.CategoryID = c.CategoryID
INNER JOIN SubCategoryVersion scv ON sc.SubCategoryID = scv.SubCategoryID 
INNER JOIN SubCategoryItem sci ON sci.SubCategoryVID = scv.SubCategoryVID 
INNER JOIN ItemCategory ic ON ic.ItemID = sci.ItemID 
INNER JOIN Category c2 ON c2.CategoryID=ic.CategoryID 
WHERE scv.EndReleaseID is NULL AND ic.EndReleaseID is NULL 
AND ic.StartReleaseID = @CurrentRelease 
AND NOT 
(
(sc.CategoryID=ic.CategoryID AND sc.CategoryID not in (Select SuperCategoryID from SuperCategoryComposition) )
OR 
(sc.CategoryID in (Select SuperCategoryID from SuperCategoryComposition) 
AND ((ic.CategoryID=sc.CategoryID) 
      OR 
	  ic.CategoryID in (SELECT scc.CategoryID from SuperCategoryComposition scc WHERE scc.SuperCategoryID=sc.CategoryID)))
)






-- 68. When an ItemCategory or PropertyCaqtegory are changing then we have to create 
--     New ModuleVersions for any related Table where these glossary objects are currently employed
INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3
    SELECT DISTINCT 
		 '1_15'																										AS ViolationCode, 
		 'ItemCategory or PropertyCategory have changed but no New ModuleVersion has been created'					AS Violation,
		 1																											AS isBlocking,
		 sq.ModuleVID																								AS TableVID, 
		 NULL																										AS OldTableVID,
		 left(sq.Code + ' (MODULE)',40)																				AS TableCode, 
		 NULL																										AS HeaderID, 
		 left('Vers.Num:' + sq.VersionNumber,30)																	AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     NULL			      																						AS CategoryID, 
  	     NULL 																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
FROM
(
-- Contexts of HeaderVersions 
(SELECT mv.*, ic.ItemID, pc.PropertyID, ic.StartReleaseID as ItemStartRelease, pc.StartReleaseID as PropertyStartRelease 
FROM moduleversion mv 
INNER JOIN moduleversioncomposition mvc ON mv.ModuleVID = mvc.ModuleVID 
INNER JOIN TableVersion tv ON tv.TableVID = mvc.TableVID 
INNER JOIN TableVersionHeader tvh ON tvh.TableVID = tv.TableVID 
INNER JOIN HeaderVersion hv ON hv.HeaderVID = tvh.HeaderVID 
INNER JOIN ContextComposition cc ON cc.ContextID = hv.ContextID 
INNER JOIN ItemCategory ic ON ic.ItemID = cc.PropertyID 
INNER JOIN PropertyCategory pc ON pc.PropertyID = cc.PropertyID 
WHERE mv.EndReleaseID is NULL AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL AND
(ic.StartReleaseID = @CurrentRelease OR pc.StartReleaseID=@CurrentRelease) 
AND mv.StartReleaseID <> @CurrentRelease
)
UNION
-- Contexts of TableVersions 
(SELECT mv.*, ic.ItemID, pc.PropertyID, ic.StartReleaseID as ItemStartRelease, pc.StartReleaseID as PropertyStartRelease 
FROM moduleversion mv 
INNER JOIN moduleversioncomposition mvc ON mv.ModuleVID = mvc.ModuleVID 
INNER JOIN TableVersion tv ON tv.TableVID = mvc.TableVID 
INNER JOIN ContextComposition cc ON cc.ContextID = tv.ContextID 
INNER JOIN ItemCategory ic ON ic.ItemID = cc.PropertyID 
INNER JOIN PropertyCategory pc ON pc.PropertyID = cc.PropertyID 
WHERE mv.EndReleaseID is NULL AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL AND
(ic.StartReleaseID = @CurrentRelease OR pc.StartReleaseID=@CurrentRelease) 
AND mv.StartReleaseID <> @CurrentRelease
)
UNION
-- Contexts of VariableVersions 
(SELECT mv.*, ic.ItemID, pc.PropertyID, ic.StartReleaseID as ItemStartRelease, pc.StartReleaseID as PropertyStartRelease 
FROM moduleversion mv 
INNER JOIN moduleversioncomposition mvc ON mv.ModuleVID = mvc.ModuleVID 
INNER JOIN TableVersion tv ON tv.TableVID = mvc.TableVID 
INNER JOIN TableVersionCell tvc ON tv.TableVID = tvc.TableVID 
INNER JOIN VariableVersion vv ON tvc.VariableVID = vv.VariableVID 
INNER JOIN ContextComposition cc ON cc.ContextID = vv.ContextID 
INNER JOIN ItemCategory ic ON ic.ItemID = cc.PropertyID 
INNER JOIN PropertyCategory pc ON pc.PropertyID = cc.PropertyID 
WHERE mv.EndReleaseID is NULL AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL AND
(ic.StartReleaseID = @CurrentRelease OR pc.StartReleaseID=@CurrentRelease) 
AND mv.StartReleaseID <> @CurrentRelease
)
UNION
-- Properties of HeaderVersions 
(SELECT mv.*, ic.ItemID, pc.PropertyID, ic.StartReleaseID as ItemStartRelease, pc.StartReleaseID as PropertyStartRelease 
FROM moduleversion mv 
INNER JOIN moduleversioncomposition mvc ON mv.ModuleVID = mvc.ModuleVID 
INNER JOIN TableVersion tv ON tv.TableVID = mvc.TableVID 
INNER JOIN TableVersionHeader tvh ON tvh.TableVID = tv.TableVID 
INNER JOIN HeaderVersion hv ON hv.HeaderVID = tvh.HeaderVID 
INNER JOIN ItemCategory ic ON ic.ItemID = hv.PropertyID 
INNER JOIN PropertyCategory pc ON pc.PropertyID = hv.PropertyID 
WHERE mv.EndReleaseID is NULL AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL AND
(ic.StartReleaseID = @CurrentRelease OR pc.StartReleaseID=@CurrentRelease) 
AND mv.StartReleaseID <> @CurrentRelease
)
UNION
-- Properties of TableVersions 
(SELECT mv.*, ic.ItemID, pc.PropertyID, ic.StartReleaseID as ItemStartRelease, pc.StartReleaseID as PropertyStartRelease 
FROM moduleversion mv 
INNER JOIN moduleversioncomposition mvc ON mv.ModuleVID = mvc.ModuleVID 
INNER JOIN TableVersion tv ON tv.TableVID = mvc.TableVID 
INNER JOIN ItemCategory ic ON ic.ItemID = tv.PropertyID 
INNER JOIN PropertyCategory pc ON pc.PropertyID = tv.PropertyID 
WHERE mv.EndReleaseID is NULL AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL AND
(ic.StartReleaseID = @CurrentRelease OR pc.StartReleaseID=@CurrentRelease) 
AND mv.StartReleaseID <> @CurrentRelease
)
UNION
-- Properties of VariableVersions 
(SELECT mv.*, ic.ItemID, pc.PropertyID, ic.StartReleaseID as ItemStartRelease, pc.StartReleaseID as PropertyStartRelease 
FROM moduleversion mv 
INNER JOIN moduleversioncomposition mvc ON mv.ModuleVID = mvc.ModuleVID 
INNER JOIN TableVersion tv ON tv.TableVID = mvc.TableVID 
INNER JOIN TableVersionCell tvc ON tv.TableVID = tvc.TableVID 
INNER JOIN VariableVersion vv ON tvc.VariableVID = vv.VariableVID 
INNER JOIN ItemCategory ic ON ic.ItemID = vv.PropertyID 
INNER JOIN PropertyCategory pc ON pc.PropertyID = vv.PropertyID 
WHERE mv.EndReleaseID is NULL AND ic.EndReleaseID is NULL AND pc.EndReleaseID is NULL AND
(ic.StartReleaseID = @CurrentRelease OR pc.StartReleaseID=@CurrentRelease) 
AND mv.StartReleaseID <> @CurrentRelease
)

) sq 
INNER JOIN ItemCategory icin on icin.ItemID=sq.ItemID and icin.EndReleaseID is Null 
INNER JOIN ItemCategory icpr on icpr.ItemID=sq.PropertyID and icpr.EndReleaseID is Null 





-- 69. All Properties in any non-Enumerated Category (except _PR and _NA) must belong to one common Data type	
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '6_24'																										AS ViolationCode, 
		 LEFT('Properties from Non-Enumerated Category (except _PR and _NA) belong to more than one data Types; majority Data Type is :' + dt2.name,255) AS Violation,
		 1																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 left('Property Current Datatype:'+dt.Name, 60)																AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID 
  INNER JOIN DataType dt ON p.DataTypeID = dt.DataTypeID, 
  DataType dt2 
  WHERE c.IsEnumerated=0 AND 
  c.Code NOT IN ('_NA', '_PR') AND 
  pc.EndReleaseID is NULL AND 
  p.DataTypeID<>dt2.DataTypeID AND 
  dt2.DataTypeID in (SELECT p2.DataTypeID 
                     from PropertyCategory pc2 
					 JOIN Property p2 ON pc2.PropertyID=p2.PropertyID 
                     WHERE pc2.CategoryID=c.CategoryID 
					 and pc2.PropertyID <> pc.PropertyID 
					 and p2.datatypeID <>  p.DataTypeID  
					 AND (
					      (SELECT count(pc3.PropertyID) 
						   from Propertycategory pc3 
						   inner join Property p3 on pc3.PropertyID = p3.PropertyID 
					       WHERE pc3.EndReleaseID is Null 
						   and pc3.categoryID = c.CategoryID 
						   and p3.dataTypeID=p2.dataTypeID
						  )
>=(0.5 * 
						 (SELECT count(pc4.PropertyID) 
						  from   Propertycategory pc4 
						  where  pc4.EndReleaseID is Null 
						  and pc4.categoryID=c.CategoryID))))





  
-- 70. A Property Name has to be Unique
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 2
    SELECT DISTINCT 
		 '6_25'																										AS ViolationCode, 
		 'Property Name is not Unique: '+left(it.Name,180)															AS Violation,
		 0																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN Item it ON it.ItemID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID 
  WHERE  
  pc.StartReleaseID=@CurrentRelease 
  AND pc.EndReleaseID is NULL 
  AND ic.EndReleaseID is NULL 
  AND EXISTS (SELECT * FROM 
			  PropertyCategory pc2 INNER JOIN ItemCategory ic2 ON pc2.PropertyID=ic2.ItemID 
			  INNER JOIN Item it2 ON it2.ItemID = ic2.ItemID
			  WHERE pc2.EndReleaseID is NULL AND ic2.EndReleaseID is NULL 
			  AND pc2.PropertyID<>p.PropertyID 
			  AND trim(it2.Name)=trim(it.Name) 
			 ) 
  
  
  
  



-- 71. An Item Name has to be Unique within its Category
  INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3
    SELECT DISTINCT 
		 '6_26'																										AS ViolationCode, 
		 left('Item Name is not Unique within its Category itself: '+trim(it.Name),255)								AS Violation,
		 0																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 NULL																										AS HeaderPropertyID, 
		 NULL																										AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 NULL																										AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 it.ItemID																									AS ItemID,
		 ic.Code																									AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   ItemCategory ic INNER JOIN Item it ON it.ItemID=ic.ItemID 
  INNER JOIN Category c ON ic.CategoryID=c.CategoryID
  WHERE  
  it.IsProperty = 0 
  AND ic.StartReleaseID=@CurrentRelease 
  AND ic.EndReleaseID is NULL 
  AND EXISTS (SELECT * FROM 
			  ItemCategory ic2 INNER JOIN Item it2 ON it2.ItemID = ic2.ItemID 
			  WHERE ic2.EndReleaseID is NULL 
			  AND it2.ItemID<>it.ItemID 
			  AND trim(it2.Name)=trim(it.Name) 
			  AND ic2.CategoryID = ic.CategoryID 
			 ) 
  
    
-- 72.	Any default Item must not appear in the Context of any Table corresponding to a Module updated in the Current Release
-- First on HeaderVersion
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '4_9'														AS ViolationCode, 
		 'Default Item appears in Context of a Table from a module updated in Current Release'	AS Violation,
		 0															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 NULL														AS OldTableVID,
		 tv.Code													AS TableCode, 
		 h.HeaderID													AS HeaderID, 
		 hv.Code													AS HeaderCode, 
		 hv.HeaderVID												AS HeaderVID, 
		 NULL														AS  OldHeaderVID, 
		 NULL														AS KeyHeader, 
		 NULL														AS HeaderDirection, 
		 NULL														AS HeaderPropertyID, 
		 NULL														AS HeaderPropertyCode, 
		 NULL														AS HeaderSubcategoryID, 
		 NULL														AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     c.CategoryID  												AS CategoryID, 
  	     c.Code														AS CategoryCode, 
		 itc.ItemID													AS  ItemID,
		 itc.Code													AS  ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc ON mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion]			mv	ON mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h	ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   [ContextComposition]	cc	ON (hv.ContextID	= cc.ContextID) 
  JOIN   [ItemCategory]			itc ON (itc.ItemID		= cc.ItemID)
  JOIN   [Category]				c	ON (itc.CategoryID	= c.CategoryID) 
  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 h.isKey		 = 0
  AND	 tvh.isAbstract  = 0
  AND	 c.IsEnumerated  = 1 
  AND    itc.EndReleaseID is NULL 
  AND	 itc.IsDefaultItem = 1
  ORDER BY tv.TableVID

-- Secondly on TableVersion
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '4_9'														AS ViolationCode, 
		 'Default Item appears in Context of a Table from a module updated in Current Release'	AS Violation,
		 0															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 NULL														AS OldTableVID,
		 tv.Code													AS TableCode, 
		 NULL														AS HeaderID, 
		 NULL														AS HeaderCode, 
		 NULL														AS HeaderVID, 
		 NULL														AS  OldHeaderVID, 
		 NULL														AS KeyHeader, 
		 NULL														AS HeaderDirection, 
		 NULL														AS HeaderPropertyID, 
		 NULL														AS HeaderPropertyCode, 
		 NULL														AS HeaderSubcategoryID, 
		 NULL														AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     c.CategoryID  												AS CategoryID, 
  	     c.Code														AS CategoryCode, 
		 itc.ItemID													AS  ItemID,
		 itc.Code													AS  ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc ON mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion]			mv	ON mv.ModuleVID = mvc.ModuleVID
  JOIN   [ContextComposition]	cc	ON (tv.ContextID	= cc.ContextID) 
  JOIN   [ItemCategory]			itc ON (itc.ItemID		= cc.ItemID)
  JOIN   [Category]				c	ON (itc.CategoryID	= c.CategoryID) 
  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 c.IsEnumerated  = 1 
  AND    itc.EndReleaseID is NULL 
  AND	 itc.IsDefaultItem = 1
  ORDER BY tv.TableVID


-- Finally on CompoundItemContext 
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '4_9'														AS ViolationCode, 
		 'Default Item appears in Context of a CompoundItem updated in Current Release'	AS Violation,
		 0															AS isBlocking,
		 NULL														AS TableVID, 
		 NULL														AS OldTableVID,
		 'Comp Item: '+ic0.Code										AS TableCode, 
		 NULL														AS HeaderID, 
		 'Item Categ:'+c0.Code										AS HeaderCode, 
		 NULL														AS HeaderVID, 
		 NULL														AS  OldHeaderVID, 
		 NULL														AS KeyHeader, 
		 NULL														AS HeaderDirection, 
		 NULL														AS HeaderPropertyID, 
		 NULL														AS HeaderPropertyCode, 
		 NULL														AS HeaderSubcategoryID, 
		 NULL														AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     c.CategoryID  												AS CategoryID, 
  	     c.Code														AS CategoryCode, 
		 itc.ItemID													AS  ItemID,
		 itc.Code													AS  ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [Item]					it0 
  JOIN   [ItemCategory]			ic0  ON (it0.ItemID		= ic0.ItemID)
  JOIN   [Category]				c0   ON (ic0.CategoryID	= c0.CategoryID) 
  JOIN   [CompoundItemContext]	cic  ON (cic.ItemID		= it0.ItemID) 
  JOIN   [ContextComposition]	cc	ON (cic.ContextID	= cc.ContextID) 
  JOIN   [ItemCategory]			itc ON (itc.ItemID		= cc.ItemID)
  JOIN   [Category]				c	ON (itc.CategoryID	= c.CategoryID) 
  WHERE  cic.StartReleaseID = @CurrentRelease 
  AND	 c.IsEnumerated  = 1 
  AND    itc.EndReleaseID is NULL 
  AND	 itc.IsDefaultItem = 1



  -- 73.	An attribute header must be associated to another header (key or non key) of the same direction of the same TableVersion 
  --        that is also employed by the latest tableversion
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '3_10'															AS ViolationCode, 
		 'Attribute Header not associated with a Unique other active Header of the Same Direction of the Table'	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 hv.HeaderID													AS HeaderID, 
		 left('Attr_Header:'+hv.Code,30)								AS HeaderCode, 
		 hv.HeaderVID													AS HeaderVID, 
		 NULL															AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 NULL															AS HeaderPropertyID, 
		 NULL															AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     NULL		  													AS CategoryID, 
  	     NULL															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t   ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h   ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
		  								tvh.HeaderVID	= hv.HeaderVID 
		  							  AND 
		  								tvh.TableVID	= tv.TableVID
		  							   ) 
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND	 hv.EndReleaseID	IS NULL
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isAttribute		= 1
  AND	 tvh.isAbstract		= 0
  AND	 1  <>  (SELECT count(distinct cr.ConceptRelationID) 
                 FROM   [TableVersionHeader] tvh2 
				 JOIN   [HeaderVersion] hv2	on hv2.HeaderVID  = tvh2.HeaderVID 
				 JOIN   [Header] h2			on h2.HeaderID  = hv2.HeaderID 
				 JOIN   [RelatedConcept] rc	on rc.ConceptGUID = h.RowGUID and rc.IsRelatedConcept = 1 
				 JOIN   [RelatedConcept] rc2	on rc2.ConceptGUID = h2.RowGUID and rc2.IsRelatedConcept = 0 and rc.ConceptRelationID = rc2.ConceptRelationID 
				 JOIN   [ConceptRelation] cr	on cr.ConceptRelationID = rc.ConceptRelationID and cr.Type='header_attributeHeader' 
  				 WHERE  tvh2.TableVID  = tvh.TableVID 
  				 AND	h2.Direction = h.Direction 
				)
  ORDER BY tv.TableVID, 
		   h.Direction;


  -- 74.	The only Direction that is allowed to define Attributes for Fact Headers is the direction where the Main Property of Fact Headers is defined.
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '3_11'															AS ViolationCode, 
		 'Definition of Attributes for Fact Headers on a direction on which Main Property is not defined'	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 hv.HeaderID													AS HeaderID, 
		 left('Attr_Header:'+hv.Code,30)								AS HeaderCode, 
		 hv.HeaderVID													AS HeaderVID, 
		 NULL															AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 NULL															AS HeaderPropertyID, 
		 NULL															AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     NULL		  													AS CategoryID, 
  	     NULL															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t   ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h   ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
		  								tvh.HeaderVID	= hv.HeaderVID 
		  							  AND 
		  								tvh.TableVID	= tv.TableVID
		  							   ) 
  JOIN   [TableVersionHeader] tvh2 ON tvh2.TableVID  = tvh.TableVID
  JOIN   [HeaderVersion] hv2	on hv2.HeaderVID  = tvh2.HeaderVID 
  JOIN   [Header] h2			on h2.HeaderID  = hv2.HeaderID 
  JOIN   [RelatedConcept] rc	on rc.ConceptGUID = h.RowGUID and rc.IsRelatedConcept = 1 
  JOIN   [RelatedConcept] rc2	on rc2.ConceptGUID = h2.RowGUID and rc2.IsRelatedConcept = 0 and rc.ConceptRelationID = rc2.ConceptRelationID 
  JOIN   [ConceptRelation] cr	on cr.ConceptRelationID = rc.ConceptRelationID and cr.Type='header_attributeHeader'
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND	 hv.EndReleaseID	IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isAttribute		= 1
  AND	 tvh.isAbstract		= 0
  AND    h2.IsKey = 0
  AND    hv2.PropertyID is NULL
  ORDER BY tv.TableVID, 
		   h.Direction;


  -- 75.	The only Direction that is allowed to define Attributes for Key Headers is the direction where the Key Header is defined.
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '3_12'															AS ViolationCode, 
		 'Definition of Attributes for Key Headers on a direction different than that of the Key Header'	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 hv.HeaderID													AS HeaderID, 
		 left('Attr_Header:'+hv.Code,30)								AS HeaderCode, 
		 hv.HeaderVID													AS HeaderVID, 
		 NULL															AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 NULL															AS HeaderPropertyID, 
		 NULL															AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     NULL		  													AS CategoryID, 
  	     NULL															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t   ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h   ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
		  								tvh.HeaderVID	= hv.HeaderVID 
		  							  AND 
		  								tvh.TableVID	= tv.TableVID
		  							   ) 
  JOIN   [TableVersionHeader] tvh2 ON tvh2.TableVID  = tvh.TableVID
  JOIN   [HeaderVersion] hv2	on hv2.HeaderVID  = tvh2.HeaderVID 
  JOIN   [Header] h2			on h2.HeaderID  = hv2.HeaderID 
  JOIN   [RelatedConcept] rc	on rc.ConceptGUID = h.RowGUID and rc.IsRelatedConcept = 1 
  JOIN   [RelatedConcept] rc2	on rc2.ConceptGUID = h2.RowGUID and rc2.IsRelatedConcept = 0 and rc.ConceptRelationID = rc2.ConceptRelationID 
  JOIN   [ConceptRelation] cr	on cr.ConceptRelationID = rc.ConceptRelationID and cr.Type='header_attributeHeader'
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND	 hv.EndReleaseID	IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isAttribute		= 1
  AND	 tvh.isAbstract		= 0
  AND    h2.IsKey = 1
  AND    h2.Direction <> h.Direction 
  ORDER BY tv.TableVID, 
		   h.Direction;



-- 76.	An Attribute Header is not allowed to change Main Property with a different Data Type than the previous version
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '3_14'															AS ViolationCode, 
		 'Attribute Header Main Property data Type: ' + dt.Code + ' is Different than that of Previous Version:'+dt3.Code	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 hv.HeaderID													AS HeaderID, 
		 left('Attr_Header:'+hv.Code,30)								AS HeaderCode, 
		 hv.HeaderVID													AS HeaderVID, 
		 NULL															AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 NULL															AS HeaderPropertyID, 
		 NULL															AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     NULL		  													AS CategoryID, 
  	     NULL															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t   ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h   ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
		  								tvh.HeaderVID	= hv.HeaderVID 
		  							  AND 
		  								tvh.TableVID	= tv.TableVID
		  							   ) 
  JOIN   [HeaderVersion] hv3	on hv3.HeaderID  = hv.HeaderID AND hv3.EndReleaseID = @CurrentRelease 
  JOIN   [Property] p			on p.PropertyID = hv.PropertyID
  JOIN   [DataType] dt   	    on dt.DataTypeID = p.DataTypeID 
  JOIN   [Property] p3			on p3.PropertyID = hv3.PropertyID
  JOIN   [DataType] dt3   	    on dt3.DataTypeID = p3.DataTypeID 
  JOIN   [TableVersionHeader] tvh2 ON tvh2.TableVID  = tvh.TableVID
  JOIN   [HeaderVersion] hv2	on hv2.HeaderVID  = tvh2.HeaderVID 
  JOIN   [Header] h2			on h2.HeaderID  = hv2.HeaderID 
  JOIN   [RelatedConcept] rc	on rc.ConceptGUID = h.RowGUID and rc.IsRelatedConcept = 1 
  JOIN   [RelatedConcept] rc2	on rc2.ConceptGUID = h2.RowGUID and rc2.IsRelatedConcept = 0 and rc.ConceptRelationID = rc2.ConceptRelationID 
  JOIN   [ConceptRelation] cr	on cr.ConceptRelationID = rc.ConceptRelationID and cr.Type='header_attributeHeader'
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND	 hv.EndReleaseID	IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h.isAttribute		= 1
  AND	 tvh.isAbstract		= 0 
  AND    p.DataTypeID <> p3.DataTypeID
  ORDER BY tv.TableVID, 
		   h.Direction;




-- 77.	A Fact or Key Header which has an associated Attribute is not allowed to change Main or Key Property with a different Data Type than the previous version
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 3  
  SELECT DISTINCT 
		 '3_15'															AS ViolationCode, 
		 'Header with an associated Attribute changed Property with Current data Type:' + dt.Code + ' which is Different than that of Previous Data Type:'+dt3.Code	AS Violation,
		 1																AS isBlocking,
		 tv.TableVID													AS TableVID, 
		 NULL															AS OldTableVID,
		 tv.Code														AS TableCode, 
		 hv.HeaderID													AS HeaderID, 
		 left('Attr_Header:'+hv.Code,30)								AS HeaderCode, 
		 hv.HeaderVID													AS HeaderVID, 
		 NULL															AS OldHeaderVID, 
		 NULL															AS KeyHeader, 
		 h.Direction													AS HeaderDirection, 
		 NULL															AS HeaderPropertyID, 
		 NULL															AS HeaderPropertyCode, 
		 NULL															AS HeaderSubcategoryID, 
		 NULL															AS HeaderSubcategoryName, 
		 NULL															AS HeaderContextID, 
  	     NULL		  													AS CategoryID, 
  	     NULL															AS CategoryCode, 
		 NULL															AS ItemID,
		 NULL															AS ItemCode,
		 NULL															AS CellID,
		 NULL															AS CellCode,
		 NULL															AS Ceell2ID,
		 NULL															AS Cell2Code,
		 NULL															AS VVEndReleaseID,
		 NULL															AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t   ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc on mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion] mv on mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h   ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv  ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
		  								tvh.HeaderVID	= hv.HeaderVID 
		  							  AND 
		  								tvh.TableVID	= tv.TableVID
		  							   ) 
  JOIN   [HeaderVersion] hv3	on hv3.HeaderID  = hv.HeaderID AND hv3.EndReleaseID = @CurrentRelease 
  JOIN   [Property] p			on p.PropertyID = hv.PropertyID
  JOIN   [DataType] dt   	    on dt.DataTypeID = p.DataTypeID 
  JOIN   [Property] p3			on p3.PropertyID = hv3.PropertyID
  JOIN   [DataType] dt3   	    on dt3.DataTypeID = p3.DataTypeID 
  JOIN   [TableVersionHeader] tvh2 ON tvh2.TableVID  = tvh.TableVID
  JOIN   [HeaderVersion] hv2	on hv2.HeaderVID  = tvh2.HeaderVID 
  JOIN   [Header] h2			on h2.HeaderID  = hv2.HeaderID 
  JOIN   [RelatedConcept] rc	on rc.ConceptGUID = h.RowGUID and rc.IsRelatedConcept = 0 
  JOIN   [RelatedConcept] rc2	on rc2.ConceptGUID = h2.RowGUID and rc2.IsRelatedConcept = 1 and rc.ConceptRelationID = rc2.ConceptRelationID 
  JOIN   [ConceptRelation] cr	on cr.ConceptRelationID = rc.ConceptRelationID and cr.Type='header_attributeHeader'
  WHERE  t.IsAbstract		= 0
  AND	 tv.EndReleaseID	IS NULL
  AND	 hv.EndReleaseID	IS NULL 
  AND    tv.StartReleaseID = @CurrentRelease 
  AND	 h2.isAttribute		= 1
  AND	 tvh.isAbstract		= 0 
  AND    p.DataTypeID <> p3.DataTypeID
  ORDER BY tv.TableVID, 
		   h.Direction;


-- 78. A Property that isMetric has obligatorily to contain a non-Null PeriodType (stock or flow)
INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3
    SELECT DISTINCT 
		 '6_27'																										AS ViolationCode, 
		 left('Property isMetric but has NULL  PeriodType (periodtype has to be: stock or flow)',255)						AS Violation,
		 1																											AS isBlocking,
		 NULL																										AS TableVID, 
		 NULL																										AS OldTableVID,
		 NULL																										AS TableCode, 
		 NULL																										AS HeaderID, 
		 NULL																										AS HeaderCode, 
		 NULL																										AS HeaderVID, 
		 NULL																										AS OldHeaderVID, 
		 NULL																										AS KeyHeader, 
		 NULL																										AS HeaderDirection, 
		 p.PropertyID																								AS HeaderPropertyID, 
		 ic.Code																									AS HeaderPropertyCode, 
		 NULL				  																						AS HeaderSubcategoryID, 
		 left('datatype:'+dt.code+' Flowtype:'+p.PeriodType,60)														AS HeaderSubcategoryName, 
		 NULL																										AS HeaderContextID, 
  	     c.CategoryID	      																						AS CategoryID, 
  	     c.Code																										AS CategoryCode, 
		 NULL																										AS ItemID,
		 NULL																										AS ItemCode,
		 NULL																										AS CellID,
		 NULL																										AS CellCode,
		 NULL																										AS Ceell2ID,
		 NULL																										AS Cell2Code,
		 NULL																										AS VVEndReleaseID,
		 NULL																										AS NewAspect
  FROM   Property p 
  INNER JOIN ItemCategory ic ON p.PropertyID=ic.ItemID 
  INNER JOIN PropertyCategory pc ON p.PropertyID=pc.PropertyID 
  INNER JOIN Category c ON pc.CategoryID=c.CategoryID
  INNER JOIN DataType dt on p.DataTypeID=dt.DataTypeID 
  WHERE  pc.StartReleaseID=@CurrentRelease 
  AND pc.EndReleaseID is NULL 
  AND ic.EndReleaseID is NULL
  AND p.IsMetric = 1 
  AND (p.periodType is NULL or p.PeriodType not in ('stock','flow'))




  -- 79  If a Cell  a void or rexcluded then we are not allowed to set any Sign on this Cell
  INSERT INTO ModelViolations (ViolationCode, Violation, isBlocking, TableVID, TableCode, CellID, CellCode)
-- DECLARE @CurrentRelease int = 3
  SELECT DISTINCT 
  '6_28' as ViolationCode, 
  'On this Cell there was set a Sign whilst this is Void or Exccluded' AS Violation,
  1 as isBlocking,
  tv.TableVID as TableVID, 
  tv.Code as TableCode, 
  tvc.CellID as CellID, 
  tvc.CellCode  as CellCode 
  FROM   TableVersionCell tvc 
  JOIN   TableVersion     tv  ON (tv.TableVID   = tvc.TableVID) 
  JOIN   ModuleVersionComposition mvc  ON (tv.TableVID   = mvc.TableVID) 
  JOIN   ModuleVersion mv	 ON (mv.ModuleVID   = mvc.ModuleVID) 
  WHERE  tvc.[Sign] is not null 
  AND mv.StartReleaseID=@CurrentRelease
  AND (tvc.isVoid=1 OR tvc.isExcluded=1)	 
  ORDER BY tv.TableVID, 
		   tvc.CellCode;



-- 80.	A SubCategory that appears on a Header must not Include a Default Item in its composition
  INSERT INTO ModelViolations 
-- DECLARE @CurrentRelease int = 4  
  SELECT DISTINCT 
		 '4_10'														AS ViolationCode, 
		 'Default Item appears in the Composition of a SubCategory associated with a Header'	AS Violation,
		 1															AS isBlocking,
		 tv.TableVID												AS TableVID, 
		 NULL														AS OldTableVID,
		 tv.Code													AS TableCode, 
		 h.HeaderID													AS HeaderID, 
		 hv.Code													AS HeaderCode, 
		 hv.HeaderVID												AS HeaderVID, 
		 NULL														AS  OldHeaderVID, 
		 h.isKey													AS KeyHeader, 
		 h.Direction												AS HeaderDirection, 
		 hv.PropertyID												AS HeaderPropertyID, 
		 itp.Code													AS HeaderPropertyCode, 
		 sc.SubCategoryID											AS HeaderSubcategoryID, 
		 sc.Code													AS HeaderSubcategoryName, 
		 NULL														AS HeaderContextID, 
  	     c.CategoryID  												AS CategoryID, 
  	     left('PropertyCategoryCode: '+c.Code,50)					AS CategoryCode, 
		 itc.ItemID													AS  ItemID,
		 left('Default_ItemCode:'+itc.Code,30)						AS  ItemCode,
		 NULL														AS CellID,
		 NULL														AS CellCode,
		 NULL														AS Ceell2ID,
		 NULL														AS Cell2Code,
		 NULL														AS VVEndReleaseID,
		 NULL														AS NewAspect
  FROM   [TableVersion]			tv 
  JOIN   [Table]				t	ON (t.TableID		= tv.TableID) 
  JOIN [ModuleVersionComposition] mvc ON mvc.TableVID = tv.TableVID 
  JOIN [ModuleVersion]			mv	ON mv.ModuleVID = mvc.ModuleVID
  JOIN   [Header]				h	ON (h.TableID		= t.TableID) 
  JOIN   [HeaderVersion]		hv	ON (hv.HeaderID		= h.HeaderID)
  JOIN   [TableVersionHeader]	tvh ON (
										tvh.HeaderVID	= hv.HeaderVID 
									  AND 
									    tvh.TableVID	= tv.TableVID
									   )
  JOIN   [SubCategoryVersion]	scv ON (hv.SubCategoryVID=scv.SubCategoryVID)
  JOIN   [SubCategory]			sc	ON (sc.SubCategoryID=scv.SubCategoryID)
  JOIN   [SubCategoryItem]		sci	ON (scv.SubCategoryVID=sci.SubCategoryVID) 
  JOIN   [ItemCategory]			itc ON (itc.ItemID		= sci.ItemID)
  JOIN   [ItemCategory]			itp ON (itp.ItemID		= hv.PropertyID)
  JOIN   [Property]				p	ON (p.PropertyID    = hv.PropertyID)
  JOIN   [PropertyCategory]		pc	ON (p.PropertyID    = pc.PropertyID)
  JOIN   [Category]				c	ON (pc.CategoryID	= c.CategoryID) 
  WHERE  t.IsAbstract	 = 0
  AND	 tv.EndReleaseID IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 tvh.isAbstract  = 0
  AND    itc.EndReleaseID is NULL 
  AND    itp.EndReleaseID is NULL 
  AND    pc.EndReleaseID is NULL 
  AND	 itc.IsDefaultItem = 1
  ORDER BY tv.TableVID


  --select * from [table] t inner join tableversion tv on t.TableID=tv.tableid where tv.code like 'C_07.00%' and t.IsAbstract=0 and tv.EndReleaseID is null


-- 81. The Order of a Header should be in accordance of the Order of its Parent and the ParentFirst specification
  INSERT INTO ModelViolations 
--DECLARE @CurrentRelease int = 4  
  SELECT DISTINCT 
		 '3_15'																AS ViolationCode, 
		 'The Order of a Header violates ParentFirst specification. '+
		 'Child_Order='+cast(tvh.[Order] as nvarchar(10))+
		 '  Parent_Order='+cast(tvh2.[Order] as nvarchar(10))+
		 '  ParentFirst='+cast(tvh2.ParentFirst as nvarchar(4)) 
																			AS Violation,
		 1																	AS isBlocking,
		 tv.TableVID														AS TableVID, 
		 NULL																AS OldTableVID,
		 tv.Code															AS TableCode, 
		 h.HeaderID															AS HeaderID, 
		 hv.Code															AS HeaderCode, 
		 NULL																AS HeaderVID, 
		 NULL																AS OldHeaderVID, 
		 NULL																AS KeyHeader, 
		 h.Direction														AS HeaderDirection, 
		 NULL																AS HeaderPropertyID, 
		 NULL																AS HeaderPropertyCode, 
		 NULL																AS HeaderSubcategoryID, 
		 NULL																AS HeaderSubcategoryName, 
		 NULL																AS HeaderContextID, 
  	     NULL       														AS CategoryID, 
  	     NULL																AS CategoryCode, 
		 NULL																AS ItemID,
		 NULL																AS ItemCode,
		 NULL																AS CellID,
		 NULL																AS CellCode,
		 NULL																AS Ceell2ID,
		 NULL																AS Cell2Code,
		 NULL																AS VVEndReleaseID,
		 NULL																AS NewAspect
  FROM   [TableVersion]				tv 
  JOIN   [Table]					t	ON (t.TableID			= tv.TableID) 
  JOIN   [Header]					h	ON (h.TableID			= t.TableID) 
  JOIN   [HeaderVersion]			hv	ON (hv.HeaderID			= h.HeaderID)
  JOIN   [TableVersionHeader]		tvh ON (
										    tvh.HeaderVID		= hv.HeaderVID 
										  AND 
										    tvh.TableVID=tv.TableVID 
										   )
  JOIN   [ModuleVersionComposition] mvc ON (tv.TableVID			= mvc.TableVID) 
  JOIN   [ModuleVersion]			mv	ON (mv.ModuleVID		= mvc.ModuleVID)
  JOIN   [TableVersionHeader]		tvh2 ON (
										    tvh2.HeaderID		= tvh.ParentHeaderID  
										  AND 
										    tvh2.TableVID=tv.TableVID 
										   )

  WHERE  t.IsAbstract    = 0
  AND	 mv.EndReleaseID IS NULL
  AND    mv.StartReleaseID = @CurrentRelease 
  AND	 hv.EndReleaseID IS NULL
  AND    ((tvh2.ParentFirst=1 AND tvh.[Order]-tvh2.[Order]<0) OR (tvh2.ParentFirst=0 AND tvh.[Order]-tvh2.[Order]>0))
  ORDER BY tv.TableVID, 
           h.Direction, 
		   h.HeaderID;





  

-- ON HOLD. On every non-abstract, non-key combination of TableVersion Headers from all the existing Table Directions, 
  --     there must corrspond one and only one TableVersionCell
  --INSERT INTO ModelViolations 
  --DECLARE @CurrentRelease int = 3
--    SELECT DISTINCT 
--		 '3_11'																										AS ViolationCode, 
--		 left('No TableVersionCell for Header Combination of the tabletype'+sq.tbltype+': ('+
--		 case when rowcode is null then '' else 'r'+sq.rowcode+', ' end + 'c' + sq.columncode + case when sheetcode is null then '' else ', s'+sq.sheetcode end 
--		 +')',255)																									AS Violation,
--		 1																											AS isBlocking,





  
  DROP TABLE IF EXISTS #datatype_mapping

   
--select * from ModelViolations where isblocking=1 and violationcode<>'1_1'
END;