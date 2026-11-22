-- =====================================================================
-- Dopisuje do plany.txt plan ostatnio wykonanej instrukcji pasującej do wzorca.
-- Wywoływany z zbierz_plany.sql:
--   @/scripts/plany/pokaz_plan.sql "T1 - Opis" "%początek tekstu zapytania%"
--   &1 - nagłówek w pliku wynikowym
--   &2 - wzorzec LIKE dopasowywany do tekstu zapytania w V$SQL
-- =====================================================================
SET TERMOUT ON
SET TIMING OFF
SET FEEDBACK OFF
SET VERIFY OFF
SET HEADING OFF
SET LINESIZE 300
SET PAGESIZE 0
SET TRIMSPOOL ON
COLUMN plan_table_output FORMAT A300

SPOOL /scripts/plany/wyniki/plany.txt APPEND
PROMPT ######################################################################
PROMPT &1
PROMPT ######################################################################
-- Pomijane są: zapytania do V$SQL, EXPLAIN PLAN oraz wewnętrzne kursory
-- Oracle oznaczone /* SQL Analyze */, które nie mają zapisanego planu.
SELECT t.plan_table_output
FROM  (SELECT sql_id, child_number
       FROM   v$sql
       WHERE  sql_text NOT LIKE '%v$sql%'
       AND    sql_text NOT LIKE 'EXPLAIN%'
       AND    sql_text NOT LIKE '/* SQL Analyze%'
       AND    sql_text LIKE '&2'
       ORDER  BY last_active_time DESC
       FETCH  FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number,
                                       'ALLSTATS LAST +COST +OUTLINE')) t;
SPOOL OFF
SET TERMOUT OFF
