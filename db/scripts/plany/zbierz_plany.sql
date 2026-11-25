-- =====================================================================
-- Zbieranie planów wykonania dla transakcji T1-T6
--
-- Uruchomienie (z katalogu głównego projektu):
--
--   1. Reset bazy do stanu wyjściowego. Usuwa wolumen z danymi, więc znikają
--      też trwałe notatki optymalizatora z poprzednich uruchomień (dyrektywy
--      planu, DBA_SQL_PLAN_DIRECTIVES), które zmieniają plany. Dane są
--      ładowane ponownie z plików CSV, więc są identyczne.
--        docker compose down -v
--        docker compose up -d
--
--   2. Poczekanie, aż baza się utworzy i załaduje dane (ok. 1-2 min).
--      W logu musi pojawić się "DATABASE IS READY TO USE!":
--        docker logs -f apteka-db
--
--   3. Zebranie planów (w kontenerze, jako SYSTEM, bo potrzebny jest dostęp
--      do V$SQL). Trwa ok. 3 min, głównie przez T1:
--        docker exec apteka-db bash -c 'sqlplus -s "system/$ORACLE_PASSWORD@localhost/FREEPDB1" @/scripts/plany/zbierz_plany.sql'
--
-- Jak to działa:
--   1. FLUSH SHARED_POOL czyści pamięć kursorów. Oracle zapamiętuje wykonane
--      zapytania i przy kolejnych uruchomieniach może zmieniać plany na
--      podstawie poprzednich wykonań. Po wyczyszczeniu każda transakcja jest
--      optymalizowana od zera, więc kolejne uruchomienia skryptu dają te
--      same plany.
--   2. CURRENT_SCHEMA = APTEKA, więc zapytania działają na tabelach aplikacji.
--   3. STATISTICS_LEVEL = ALL - baza zapisuje rzeczywiste liczby wierszy
--      (A-Rows), czasy (A-Time) i odczyty (Buffers) każdej operacji planu,
--      bez dopisywania hintu GATHER_PLAN_STATISTICS do plików transakcji.
--      Ten tryb spowalnia wykonanie, więc czasy z tego skryptu nie są
--      pomiarami wydajności.
--   4. Każda transakcja jest uruchamiana z pliku workload/tN.sql, a jej plan
--      jest odczytywany od razu po niej (pokaz_plan.sql), zanim kursor
--      zdąży wypaść z pamięci. T4-T6 kończą się ROLLBACK, więc dane się
--      nie zmieniają. T4.2 potrzebuje nagłówków z T4.1, dlatego t4.sql
--      idzie w całości.
--   5. Plan pobiera DBMS_XPLAN.DISPLAY_CURSOR(..., 'ALLSTATS LAST +COST +OUTLINE').
--
-- Wynik: /scripts/plany/wyniki/plany.txt  (na hoście db/scripts/plany/wyniki/)
-- =====================================================================

ALTER SYSTEM FLUSH SHARED_POOL;
ALTER SESSION SET CURRENT_SCHEMA = APTEKA;
ALTER SESSION SET STATISTICS_LEVEL = ALL;

-- Pusty plik wynikowy (kolejne plany są dopisywane przez pokaz_plan.sql)
SET TERMOUT OFF
SPOOL /scripts/plany/wyniki/plany.txt
SPOOL OFF

@/scripts/workload/t1.sql
@/scripts/plany/pokaz_plan.sql "T1 - Analiza sprzedaży leków na ból głowy (SELECT)" "%WITH sprzedaz_lekow AS%"

@/scripts/workload/t2.sql
@/scripts/plany/pokaz_plan.sql "T2 - Analiza producentów (SELECT)" "%WITH sprzedaz_lek_msc AS%"

@/scripts/workload/t3.sql
@/scripts/plany/pokaz_plan.sql "T3 - Najczęściej sprzedawane leki (SELECT)" "%WITH sprzedaz_miesieczna AS%"

@/scripts/workload/t4.sql
@/scripts/plany/pokaz_plan.sql "T4.1 - Nagłówki zamówień (INSERT)" "%INSERT INTO Zamowienie (%"
@/scripts/plany/pokaz_plan.sql "T4.2 - Pozycje zamówień (INSERT)" "%INSERT INTO PozycjaZamowienia (%"
@/scripts/plany/pokaz_plan.sql "T4.3 - Wartość nowych zamówień (UPDATE)" "%UPDATE Zamowienie z%"

@/scripts/workload/t5.sql
@/scripts/plany/pokaz_plan.sql "T5 - Aktualizacja cen leków (UPDATE)" "%UPDATE Lek l%"

@/scripts/workload/t6.sql
@/scripts/plany/pokaz_plan.sql "T6 - Usuwanie pozycji sprzedaży (DELETE)" "%DELETE FROM PozycjaSprzedazy%"

EXIT
