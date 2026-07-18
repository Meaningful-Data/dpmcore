

BEGIN

  DECLARE @fkname nvarchar(200);
  DECLARE @qry    nvarchar(1000);

  DECLARE getFKs CURSOR FOR
    SELECT CAST(fk.name AS nvarchar) fkname, N'ALTER TABLE [dbo].[' + CAST(o.name AS nvarchar) + N'] DROP CONSTRAINT ' + CAST(fk.name AS nvarchar) + N';' dropFK	   
    FROM sys.foreign_keys AS fk
    join sys.foreign_key_columns fkc ON (fkc.constraint_object_id = fk.object_id)
    JOIN sys.objects AS o  ON fk.parent_object_id     = o.object_id
    JOIN sys.objects AS o2 ON fk.referenced_object_id = o2.object_id
    join sys.columns AS o3 ON (o3.object_id = fkc.parent_object_id AND o3.column_id     = fkc.parent_column_id) 
    join sys.columns AS o4 ON (o4.object_id = fkc.referenced_object_id AND o4.column_id = fkc.referenced_column_id) 
    ORDER BY o.name, fk.name

  OPEN getFKs

  FETCH NEXT FROM getFKs INTO @fkname, @qry

  WHILE @@FETCH_STATUS = 0
  BEGIN
  
    PRINT N'Dropping FK ' + @fkname;
    exec sp_executesql @qry;
    FETCH NEXT FROM getFKs INTO @fkname, @qry;
  END;

  CLOSE getFKs;
  DEALLOCATE getFKs;
END