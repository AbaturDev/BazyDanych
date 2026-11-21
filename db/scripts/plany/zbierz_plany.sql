-- =====================================================================
-- Zbieranie planów wykonania dla transakcji T1-T6
--
-- Uruchomienie (w kontenerze, jako SYSTEM, bo potrzebny jest dostęp do V$SQL):
--   docker exec apteka-db bash -c \
--     'sqlplus -s "system/$ORACLE_PASSWORD@localhost/FREEPDB1" @/scripts/plany/zbierz_plany.sql'
--
-- Jak to działa:
--   1. CURRENT_SCHEMA = APTEKA, więc zapytania działają na tabelach aplikacji.
--   2. STATISTICS_LEVEL = ALL - baza zapisuje rzeczywiste liczby wierszy
--      (A-Rows), czasy (A-Time) i odczyty (Buffers) każdej operacji planu,
--      bez dopisywania hintu GATHER_PLAN_STATISTICS do plików transakcji.
--      Ten tryb spowalnia wykonanie, więc czasy z tego skryptu nie są
--      pomiarami wydajności.
--   3. Transakcje są uruchamiane z plików workload/tN.sql.
--      T4-T6 kończą się ROLLBACK, więc dane się nie zmieniają.
--      T4.2 potrzebuje nagłówków z T4.1, dlatego t4.sql idzie w całości.
--   4. Plan ostatniego wykonania każdej instrukcji pobiera
--      DBMS_XPLAN.DISPLAY_CURSOR(..., 'ALLSTATS LAST +COST +OUTLINE').
--
-- Wynik: /scripts/plany/wyniki/plany.txt  (na hoście db/scripts/plany/wyniki/)
-- =====================================================================

ALTER SESSION SET CURRENT_SCHEMA = APTEKA;
ALTER SESSION SET STATISTICS_LEVEL = ALL;

-- ---------------------------------------------------------------------
-- 1. Wykonanie transakcji (wyniki zapytań nie są potrzebne)
-- ---------------------------------------------------------------------
SET TERMOUT OFF
@/scripts/workload/t1.sql
@/scripts/workload/t2.sql
@/scripts/workload/t3.sql
@/scripts/workload/t4.sql
@/scripts/workload/t5.sql
@/scripts/workload/t6.sql
SET TERMOUT ON

-- ---------------------------------------------------------------------
-- 2. Plany wykonania
-- ---------------------------------------------------------------------
SET TIMING OFF
SET FEEDBACK OFF
SET VERIFY OFF
SET HEADING OFF
SET LINESIZE 300
SET PAGESIZE 0
SET TRIMSPOOL ON
COLUMN plan_table_output FORMAT A300

-- Wybiera ostatnio wykonany kursor, którego tekst pasuje do wzorca
-- (z pominięciem zapytań do V$SQL i EXPLAIN PLAN).
DEFINE plan_kursora = "FROM (SELECT sql_id, child_number FROM v$sql WHERE sql_text NOT LIKE '%v$sql%' AND sql_text NOT LIKE 'EXPLAIN%' AND sql_text LIKE"
DEFINE format_planu = "'ALLSTATS LAST +COST +OUTLINE'"

SPOOL /scripts/plany/wyniki/plany.txt

PROMPT ######################################################################
PROMPT T1 - Analiza sprzedaży leków na ból głowy (SELECT)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%WITH sprzedaz_lekow AS%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T2 - Analiza producentów (SELECT)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%WITH SprzedazLek AS%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T3 - Najczęściej sprzedawane leki (SELECT)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%WITH SprzedazLekow AS%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T4.1 - Nagłówki zamówień (INSERT)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%INSERT INTO Zamowienie (%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T4.2 - Pozycje zamówień (INSERT)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%INSERT INTO PozycjaZamowienia (%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T4.3 - Wartość nowych zamówień (UPDATE)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%UPDATE Zamowienie z%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T5 - Aktualizacja cen leków (UPDATE)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%UPDATE Lek l%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

PROMPT ######################################################################
PROMPT T6 - Usuwanie pozycji sprzedaży (DELETE)
PROMPT ######################################################################
SELECT t.plan_table_output &plan_kursora '%DELETE FROM PozycjaSprzedazy%'
       ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY) s,
       TABLE(DBMS_XPLAN.DISPLAY_CURSOR(s.sql_id, s.child_number, &format_planu)) t;

SPOOL OFF
EXIT
