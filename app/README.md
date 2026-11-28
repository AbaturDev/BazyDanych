# Faza 6: aplikacja testowa

Konsolowa aplikacja w Pythonie. Mierzy czasy wykonania transakcji T1–T6 z plików `db/scripts/workload/tN.sql`.
Budujemy ją małymi krokami. Po każdym kroku aplikacja się uruchamia, a krok trafia do osobnego commita.

## Podział pracy

**Osoba A: aplikacja.** Łączenie z bazą, wykonywanie transakcji, pomiar czasu, menu w konsoli, zapis CSV, odtwarzanie bazy od zera i opróżnianie buforów przed każdym przebiegiem.

**Osoba B: kontrola, plany i statystyki.** Kontrola stanu bazy ze wzorcem, blokada statystyk optymalizatora, plany wykonania, statystyki czasów do raportu.

**Razem:** seria pomiarów, sprawdzenie powtarzalności, wnioski.

## Kroki

### Osoba A

- [x] **Krok 1. Wykonanie transakcji z pomiarem czasu.**
  Połączenie z bazą (dane z `.env`), wczytanie `t1.sql`…`t6.sql`, wykonanie każdej instrukcji, wypisanie czasu w ms.
  Pliki: `config.py`, `transaction_loader.py`, `transaction_runner.py`, `main.py`.
- [x] **Krok 2. Menu w konsoli.**
  Wybór: jedna transakcja albo wszystkie; liczba powtórzeń. Przed każdym przebiegiem wywołanie `prepare()` (na razie puste) i nowe połączenie. Czas ROLLBACK jest wypisywany, ale nie wlicza się do czasu transakcji.
  Pliki: `main.py`, `menu.py`, `benchmark.py`, `database_preparation.py` (pusty szkielet dla B).
- [x] **Krok 3. Zapis wyników do CSV.**
  Każda instrukcja w każdym przebiegu to jeden wiersz w `app/wyniki/pomiary.csv` (format niżej). Plik jest tylko dopisywany, więc zostaje historia wszystkich serii. Zapis następuje od razu po każdej transakcji.
  Pliki: `results_writer.py` (nowy), `transaction_runner.py` (zwraca listę wyników zamiast samej sumy), `benchmark.py`, `config.py`.
- [x] **Krok 4. Nowa baza i puste bufory przed każdym przebiegiem.**
  `prepare()` przed każdym przebiegiem:
  1. `docker compose down -v` i `docker compose up -d`: baza tworzona od zera skryptami z `db/init/` i `db/startup/` (schemat, dane, stała data). Aplikacja czeka na `DATABASE IS READY TO USE!` w logu (ok. 35 s).
  2. `ALTER SYSTEM CHECKPOINT`, `FLUSH BUFFER_CACHE`, `FLUSH SHARED_POOL` jako SYSTEM.
  3. Czyszczenie pamięci podręcznej plików maszyny wirtualnej Dockera (`drop_caches`), bo dane wczytane przed chwilą tam zostają.

  Każdy przebieg jest więc „pierwszym” przebiegiem na świeżej bazie.
  Pliki: `container_control.py`, `buffer_flusher.py`, `database_preparation.py`, `config.py`.

### Osoba B

- [ ] **Krok 5. Kontrola stanu bazy przed przebiegiem.**
  Odtwarzanie bazy robi już krok 4. B sprawdza, czy po odtworzeniu stan jest taki sam jak wzorcowy: liczba wierszy, `MAX(ID)` i suma kontrolna każdej tabeli, `SYSDATE` = 2026-11-21, brak statystyk optymalizatora i dyrektyw planu. Wzorzec zapisany raz do pliku (np. `app/wyniki/stan_wzorcowy.json`). Jeśli stan się nie zgadza, `raise Exception(...)` i pomiar się nie wykona.
  Miejsce w kodzie: TODO w `database_preparation.py` (między odtworzeniem bazy a flush).
  Plik: `state_checker.py`.
- [ ] **Krok 6. Blokada statystyk.**
  Nowa baza nie ma statystyk ani dyrektyw planu, więc plany są takie same w każdym przebiegu. Ryzyko: nocne zadanie Oracle (dni robocze od 22:00) może zebrać statystyki w trakcie długiej serii. Zabezpieczenie: `DBMS_STATS.LOCK_SCHEMA_STATS('APTEKA')` po odtworzeniu bazy albo nie mierzyć wieczorem. Kontrola z kroku 5 i tak wykryje zmianę.
- [ ] **Krok 7. Plany wykonania.**
  Identyfikator planu (`plan_hash_value` z `V$SQL`) zapisywany przy każdym pomiarze. Uruchamianie `db/scripts/plany/zbierz_plany.sql` z menu.
  Plik: `plan_collector.py`.
- [ ] **Krok 8. Statystyki i tabela do raportu.**
  Wczytanie `app/wyniki/pomiary.csv` dla wybranej serii. Dla każdej transakcji i całego obciążenia: liczba uruchomień, min, max, średnia. Wynik w `app/wyniki/raport.md`.
  Plik: `statistics_report.py`.

### Razem

- [ ] **Krok 9. Pomiary i wnioski.**
  Porównanie, czy czasy i plany się powtarzają. Wnioski w raporcie.

### Format `app/wyniki/pomiary.csv`

Separator `;`. Jeden wiersz to jedna instrukcja w jednym przebiegu (T4 ma 3 wiersze: T4.1, T4.2, T4.3). ROLLBACK nie jest zapisywany.

| Kolumna | Przykład | Znaczenie | Kto wypełnia |
|---|---|---|---|
| `seria` | `2026-11-28_17-26-04` | jeden wybór w menu, identyfikator to czas startu | A |
| `przebieg` | `2` | numer powtórzenia w serii | A |
| `transakcja` | `T4` | | A |
| `instrukcja` | `T4.2` | | A |
| `czas_ms` | `1617.0` | wykonanie + pobranie wszystkich wierszy | A |
| `wiersze` | `26` | zwrócone (SELECT) lub zmienione (INSERT/UPDATE/DELETE) | A |
| `plan_hash` | `3895532130` | identyfikator planu z `V$SQL` | B (krok 7, do tego czasu puste) |

Przykład:

```
seria;przebieg;transakcja;instrukcja;czas_ms;wiersze;plan_hash
2026-11-28_17-26-04;1;T4;T4.1;1695.1;14;
2026-11-28_17-26-04;1;T4;T4.2;1567.9;26;
2026-11-28_17-26-04;1;T4;T4.3;35.7;14;
```

Czas transakcji w przebiegu = suma `czas_ms` jej instrukcji. Czas całego obciążenia = suma T1–T6 w przebiegu.

## Uruchomienie

Wszystkie polecenia wykonujemy w katalogu głównym projektu (`BD`), bo tam jest `docker-compose.yml` i `.env`.

Jednorazowo, na nowym komputerze:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt  # sterownik oracledb
cp .env.example .env                       # uzupełnić hasła
docker compose up -d                       # pierwsze utworzenie bazy
```

Uruchomienie:

```bash
.venv/bin/python -m app.main
```

- Docker Desktop musi być włączony. Kontenera nie trzeba uruchamiać ręcznie, bo aplikacja przed każdym przebiegiem sama robi `docker compose down -v` i `up -d`.
- **`down -v` usuwa bazę razem z danymi.** Dane wracają z CSV, ale ręczne zmiany w bazie przepadną.
- Za pierwszym razem Docker pobierze mały obraz `alpine` (do czyszczenia pamięci plików), więc potrzebny jest internet.
- `python app/main.py` nie zadziała (błąd `No module named 'app'`). Trzeba użyć `-m app.main`.

## Rzeczy, które już wiemy (z prób)

- **T1 trwa ok. 2 min, T6 ok. 30 s, reszta po 1–3 s.** Pełna próbka to ok. 3 min, a z odtworzeniem bazy ok. 4 min. Seria 5 przebiegów to ok. 20 min.
- **Odtworzenie bazy (`down -v` + `up -d`) trwa ok. 35 s** i daje identyczne dane (to samo CSV). Uwaga: usuwa wszystko, co było w bazie.
- **Przy wczytywaniu `tN.sql` nie wolno wycinać linii zaczynających się od `SET`.** `SET TIMING ON` to polecenie SQL*Plus i trzeba je pominąć, ale w `t5.sql` linia `SET l.CenaDetaliczna = ...` jest częścią UPDATE. Pomijamy tylko polecenia SQL*Plus: `SET TIMING`, `SET LINESIZE`, `SET PAGESIZE`.
- **Instrukcje w plikach kończą się `;`, ale do Oracle wysyłamy je bez średnika.**
- **T4–T6 kończą się `ROLLBACK`.** Dane się nie zmieniają, ale sekwencje ID tak, dlatego bazę odtwarzamy od zera (krok 4).
- **Czas transakcji nie obejmuje końcowego `ROLLBACK`** (2–15 ms). Prawdziwa aplikacja kończyłaby transakcję przez COMMIT, a ROLLBACK służy tylko do przywrócenia danych po teście. Aplikacja wypisuje go z dopiskiem `(not counted)`.
- **Bez opróżniania buforów kolejne przebiegi się różnią.** Przykład z testu T5: przebieg 1 trwał 1317 ms, przebieg 2 985 ms, bo dane były już w pamięci Oracle.
- **Sam flush nie wystarczał.** T5 trzy razy z flush, bez odtwarzania bazy: 1668, 1178, 1242 ms. Pierwszy przebieg był wolniejszy od kolejnych. Prowadzący uznaje za rzeczywisty tylko pierwszy pomiar, dlatego każdy przebieg zaczyna się od nowej bazy (krok 4).
- **Z odtwarzaniem bazy przed każdym przebiegiem czasy są równe.** T5 dwa razy: 1534 i 1485 ms (różnica 3%), za każdym razem 797 wierszy.
- **Do flush i `V$SQL` potrzebny jest SYSTEM** (`ORACLE_PASSWORD` z `.env`). Transakcje wykonuje użytkownik APTEKA.
- **Nowa baza nie ma statystyk optymalizatora**, a nocne zadanie Oracle może je zebrać i zmienić plany. Dlatego jest (opcjonalny) krok 6.
- **Baza ma stałą datę: `SYSDATE` = 2026-11-21 00:00:00** (parametr `FIXED_DATE`, skrypt `db/init/03_fixed_date.sql`). T1 i T3–T6 liczą okna dat od `SYSDATE`. Bez stałej daty każdego dnia zmieniały się wyniki i czasy, np. T5 zmieniał 750 wierszy 27.11 i 749 wierszy 28.11. Ze stałą datą T5 zawsze zmienia 797 wierszy. 21.11 to dzień zebrania planów z fazy 5.
  - Nowa baza (`docker compose down -v` i `up -d`): skrypt wykona się sam.
  - Aplikacja odtwarza bazę przed każdym przebiegiem, więc data jest zawsze ustawiona.
  - Istniejąca baza poza aplikacją: raz uruchomić `docker exec -i apteka-db sqlplus -L -s / as sysdba < db/init/03_fixed_date.sql`. Ustawienie przetrwa restart kontenera.
  - Sprawdzenie: `SELECT SYSDATE FROM dual` musi zwrócić 21.11.2026.
