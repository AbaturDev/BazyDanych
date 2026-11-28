-- Stała data w bazie: SYSDATE zawsze zwraca 2026-11-21 00:00:00.
-- Transakcje T1, T3-T6 liczą okna dat od SYSDATE ("ostatnie 12 miesięcy" itd.).
-- Bez stałej daty z każdym dniem zmieniają się zwracane wiersze i czasy wykonania.
-- 21.11.2026 to dzień zebrania planów wykonania (db/scripts/plany/wyniki/plany.txt).
--
-- Uruchamiany automatycznie przy pierwszym tworzeniu bazy (db/init/).
-- Na istniejącej bazie uruchomić ręcznie:
--   docker exec -i apteka-db sqlplus -L -s / as sysdba < db/init/03_fixed_date.sql
-- Wyłączenie:  ALTER SYSTEM SET FIXED_DATE = NONE SCOPE = BOTH;
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER SESSION SET CONTAINER = FREEPDB1;
ALTER SYSTEM SET FIXED_DATE = '2026-11-21-00:00:00' SCOPE = BOTH;
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS sysdate_w_bazie FROM dual;
EXIT
