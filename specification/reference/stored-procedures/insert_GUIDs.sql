
BEGIN 

DROP TABLE IF EXISTs #table_list

-- Get a #table_list of DPM Refit DB table names except those excluded. Also put a counter table_id on those names
SELECT table_name, 
       ROW_NUMBER() OVER(ORDER BY table_name ASC) AS table_id 
INTO   #table_list
FROM   INFORMATION_SCHEMA.TABLES
WHERE  table_type = 'BASE TABLE' 
AND    table_name NOT IN ('Concept', 'DataType', 'Operator', 'OperationNode', 'OperatorArgument', 'OperandReference', 'DPMClass', 'Language', 'Translation', 'DPMAttribute', 'SubDivisionType', 'ChangeLog', 'User', 
						  'Role', 'UserRole', 'OperandReferenceLocation', 'OperationCodePrefix', 'Aux_CellMapping', 'Aux_CellStatus', 'Aux_CellMapping', 'Aux_CellStatus',
						  'VariableGeneration', 'VarGeneration_detail', 'VarGeneration_Summary', 'OperationVersionSemanticError', 'ModelViolations', 
						  'OperationVersionData'
						  )

DECLARE @strsql  nvarchar(max) 
DECLARE @tblid   int
DECLARE @tblname nvarchar(100)
DECLARE @cnt     nvarchar(10)

exec [dbo].DisableForeignKeys;


  -- Retrieve "CurrentOwnerID"from isCurrent release. Default values are 1012 for "eba".
  DECLARE @tempOwnerID int = (SELECT max(co.OwnerID) FROM Concept co INNER JOIN Release r ON co.ConceptGUID=r.RowGUID);
  DECLARE @CurrentOwnerID int = ISNULL(@tempOwnerID, 1012);


DECLARE c1 SCROLL CURSOR FOR SELECT table_name, Table_id FROM #table_list ORDER BY table_id;

OPEN  c1;
FETCH NEXT FROM c1 INTO @tblname, @tblId
WHILE @@FETCH_STATUS = 0
BEGIN
   print @tblname
   -- We want to update 'tblname Table and add RowGUID to it using SQL function NewID() through a parametric query
   -- Is this correct? Is it properly passing the @tblname from previous query?
   SET @strsql = 'UPDATE ['+@tblname+'] SET RowGUID=NewID() WHERE RowGUID IS NULL'

   exec(@strsql)
   
   SET @cnt = CAST(@@ROWCOUNT AS nvarchar)

    print 'Update ' + @tblname + ' cnt ' + @cnt;
  -- We want to insert new RowGUIDs as ConceptGUIDs in Concept table if such ConceptGUIDs do not preexist
   -- We use table DPMClass to join @tblName = DPMClass.Name
   -- SOS!!!! TEMPORARILY WE USE OwnerID=1012 (EBA) but we need to get a clear TRACE OF OWNER!
   SET @strsql = 'INSERT INTO Concept (ConceptGUID, ClassID, OwnerID) SELECT tb.RowGUID, cl.ClassID, ' + str(@CurrentOwnerID) + ' AS OwnerID ' + 
                 'FROM [' + @tblname + '] tb, DPMClass cl ' + 
				 'WHERE cl.Name=''' +
                  + @tblname + 
			 	 ''' AND tb.RowGUID  NOT IN (SELECT ConceptGUID ' +
										    'FROM Concept) ';

   exec(@strsql)

   IF @tblname IN ('SubCategoryVersion', 'TableGroupComposition', 'TableVersionCell')
     print @strsql

   SET @cnt = CAST(@@ROWCOUNT AS nvarchar)
 
   print 'Insert into Concept from ' + @tblname + ' cnt ' + @cnt;

---   set @tblid = @tblid + 1
   FETCH NEXT FROM c1 INTO @tblname, @tblId
END

FETCH FIRST FROM c1 INTO @tblname, @tblId  --- reposition to the first record of the cursor

-- Clean GUIDs from concept table using an analogous process as in the insert.

WHILE  @@FETCH_STATUS = 0
BEGIN
   -- Clean from Concept only if this RowGUID=ConceptGUID does not exist in any @tblName record
   SET @strsql = 'DELETE cp ' + 
                 'FROM Concept cp ' + 
				 'INNER JOIN DPMClass cl ON cp.ClassID = cl.ClassID ' +
                 'WHERE cl.Name = '''+@tblname+''' ' +
				 'AND cp.ConceptGUID NOT IN (SELECT tb.RowGUID ' +
				                            'FROM ['+@tblname + '] tb)';

   exec(@strsql)

   SET @cnt = CAST(@@ROWCOUNT AS nvarchar)

   print 'Delete Concepts Not In ' + @tblname  + ' cnt ' + @cnt;

   FETCH NEXT FROM c1 INTO @tblname, @tblId
END

CLOSE c1;
DEALLOCATE c1;

exec [dbo].[EnableForeignKeys]

END