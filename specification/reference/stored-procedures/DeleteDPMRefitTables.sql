

BEGIN

  DECLARE @SchemaName nvarchar(200);
  DECLARE @TabName nvarchar(200);
  DECLARE @qry     nvarchar(1000);

  DECLARE getTabs CURSOR FOR
    SELECT CAST(s.name AS nvarchar) schemaname,
	       CAST(o.name AS nvarchar) tabname,
		   N'DELETE FROM [' + CAST(s.name AS nvarchar) + '].[' +  CAST(o.name AS nvarchar) + '];'
    FROM sys.objects o
    JOIN sys.schemas s ON (s.schema_id = o.schema_id)
    WHERE o.type = 'U'
---	AND   o.name NOT IN ('Organisation', 'DPMClass', 'Operator', 'Concept', 'DataType')
    ORDER BY o.name;

  OPEN getTabs

  FETCH NEXT FROM getTabs INTO @SchemaName, @TabName, @qry

  WHILE @@FETCH_STATUS = 0
  BEGIN
  
    PRINT N'Deleting Table ' + @SchemaName + N'.' + N'[' + @TabName + N']';
    exec sp_executesql @qry;

    FETCH NEXT FROM getTabs INTO @SchemaName, @TabName, @qry
  END;

  CLOSE getTabs;
  DEALLOCATE getTabs;
END