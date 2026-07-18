

BEGIN

  DECLARE @tabname nvarchar(200);
  DECLARE @colname nvarchar(200);
  DECLARE @qry     nvarchar(1000);

  DECLARE getCols CURSOR FOR
    SELECT o.name tabname,
	       c.name colname, 
		   N'ALTER TABLE [' + CAST(o.name AS nvarchar) + N'] ALTER COLUMN [' + CAST(c.name AS varchar) + N'] uniqueidentifier NULL;'
    FROM sys.objects o
    JOIN sys.columns c ON (c.object_id = o.object_id)
    WHERE c.name like 'RowGUID%' 	
	AND o.name != 'ChangeLog'

  OPEN getCols

  FETCH NEXT FROM getCols INTO @tabname, @colname, @qry

  WHILE @@FETCH_STATUS = 0
  BEGIN
  
    PRINT N'Setting ' + @tabname + N'.' + @colname + N' to Nullable';
    exec sp_executesql @qry;

    FETCH NEXT FROM getCols INTO @tabname, @colname, @qry
  END;

  CLOSE getCols;
  DEALLOCATE getCols;
END