# Faza 6: aplikacja testowa

Konsolowa aplikacja w Pythonie. Mierzy czasy wykonania transakcji T1–T6 z plików `db/scripts/workload/tN.sql`.
Budujemy ją małymi krokami. Po każdym kroku aplikacja się uruchamia, a krok trafia do osobnego commita.

## Wymagania z zadania i gdzie je spełniamy

| Wymóg | Krok | Osoba |
|---|---|---|
| Automatyczny pomiar czasu wykonania próbki obciążenia | 1, 2 | A |
| Wyniki każdej transakcji zapisywane automatycznie do pliku | 3 | A |
| Opróżnienie buforów bazy przed próbką | 4 | B |
| Sprawdzenie stanu danych przed każdą próbką (ten sam stan początkowy) | 5 | B |
| Powtarzalne czasy (weryfikacja na zajęciach) | 6, 9 | B, razem |
| Tabela: liczba uruchomień, min, max, średnia dla każdej transakcji i całego obciążenia | 7 | A |
| Automatyzacja zbierania planów wykonania (zalecane) | 8 | B |
| Czas próbki > 100 ms | spełnione już teraz (T1 ok. 2 min, T6 ok. 30 s) | – |
| Wnioski | 9 | razem |

## Podział pracy

**Osoba A (Aleksander): aplikacja.** Łączenie z bazą, wykonywanie transakcji, pomiar czasu, menu w konsoli, zapis CSV, statystyki do raportu.

**Osoba B: przygotowanie bazy.** Opróżnianie buforów, reset bazy, kontrola stanu, powtarzalność planów, zbieranie planów.

**Razem:** seria pomiarów, sprawdzenie powtarzalności, wnioski.

## Kroki

Kolejność ma znaczenie tylko w obrębie jednej osoby. A i B mogą pracować równolegle dzięki umowie opisanej niżej.

### Osoba A

- [x] **Krok 1. Wykonanie transakcji z pomiarem czasu.**
  Połączenie z bazą (dane z `.env`), wczytanie `t1.sql`…`t6.sql`, wykonanie każdej instrukcji, wypisanie czasu w ms.
  Pliki: `config.py`, `transaction_loader.py`, `transaction_runner.py`, `main.py`.
- [x] **Krok 2. Menu w konsoli.**
  Wybór: jedna transakcja albo wszystkie; liczba powtórzeń. Przed każdym przebiegiem wywołanie `prepare()` (na razie puste) i nowe połączenie. Czas ROLLBACK jest wypisywany, ale nie wlicza się do czasu transakcji.
  Pliki: `main.py`, `menu.py`, `benchmark.py`, `database_preparation.py` (pusty szkielet dla B).
- [ ] **Krok 3. Zapis wyników do CSV.**
  Każdy pomiar to jeden wiersz w `app/wyniki/pomiary.csv` (format niżej).
  Plik: `results_writer.py`.
- [ ] **Krok 7. Statystyki i tabela do raportu.**
  Dla każdej transakcji i całego obciążenia: liczba uruchomień, min, max, średnia. Wynik w `app/wyniki/raport.md`.
  Plik: `statistics_report.py`.

### Osoba B

- [ ] **Krok 4. Opróżnianie buforów.**
  `ALTER SYSTEM CHECKPOINT`, `ALTER SYSTEM FLUSH BUFFER_CACHE`, `ALTER SYSTEM FLUSH SHARED_POOL` jako SYSTEM.
  Plik: `database_preparation.py`.
- [ ] **Krok 5. Reset bazy i kontrola stanu.**
  Reset istniejącymi skryptami (`drop_schema.sql`, `schema.sql`, `dane.sql`, `db/startup/01_zaladuj_transakcje.sh`) przez `docker exec`.
  Po resecie porównanie stanu z zapisanym wzorcem: liczba wierszy, `MAX(ID)`, suma kontrolna każdej tabeli. Jeśli stan się nie zgadza, pomiar zostaje przerwany.
  Pliki: `database_preparation.py`, `state_checker.py`.
- [ ] **Krok 6. Powtarzalność planów.**
  Usunięcie dyrektyw planu (`DBMS_SPD`) i blokada statystyk schematu (`DBMS_STATS.LOCK_SCHEMA_STATS`). Dzięki temu nocne zadanie Oracle nie zmieni planów między naszym pomiarem a zajęciami.
  Plik: `database_preparation.py`.
- [ ] **Krok 8. Plany wykonania.**
  Identyfikator planu (`plan_hash_value` z `V$SQL`) zapisywany przy każdym pomiarze. Uruchamianie `db/scripts/plany/zbierz_plany.sql` z menu.
  Plik: `plan_collector.py`.

### Razem

- [ ] **Krok 9. Pomiary i wnioski.**
  Co najmniej dwie serie w różnym czasie. Porównanie, czy czasy i plany się powtarzają. Wnioski w raporcie.

## Umowa między A i B

A nie czeka na B. Od kroku 1 aplikacja wywołuje przed każdą próbką jedną metodę. Na początku ta metoda jest pusta, a B ją wypełnia.

```python
# app/database_preparation.py  (właściciel: B)
class DatabasePreparation:
    def prepare(self) -> None:
        """Wywoływane przez aplikację przed każdą próbką obciążenia.
        Ma zostawić bazę w stanie wzorcowym i z pustymi buforami.
        Jeśli stan się nie zgadza, rzuca wyjątek, a pomiar się nie wykonuje."""
        pass
```

Kolejność w jednej próbce (odpowiada A):

```
prepare()        <- B: reset, kontrola stanu, flush
T1 ... T6        <- A: wykonanie i pomiar
zapis do CSV     <- A
```

Bufory opróżniamy raz przed całą próbką, a nie przed każdą transakcją.

### Format `app/wyniki/pomiary.csv`

Separator `;`, jeden wiersz na transakcję w jednym przebiegu:

| Kolumna | Przykład | Kto wypełnia |
|---|---|---|
| `seria` | `2026-11-27_18-30` | A |
| `przebieg` | `3` | A |
| `transakcja` | `T4` | A |
| `czas_ms` | `1650.4` | A |
| `wiersze` | `71` | A |
| `plan_hash` | `3895532130` | B (krok 8, do tego czasu puste) |

## Struktura plików

```
app/
  README.md                  ten plik
  main.py                    A  start aplikacji, pętla menu
  menu.py                    A  wyświetlanie menu i pytania o wybór
  benchmark.py               A  przebiegi: prepare() -> nowe połączenie -> transakcje
  config.py                  A  odczyt .env (hasła, adres bazy)
  transaction_loader.py      A  wczytanie instrukcji z workload/tN.sql
  transaction_runner.py      A  wykonanie i pomiar czasu
  results_writer.py          A  zapis do CSV
  statistics_report.py       A  min/max/średnia, raport.md
  database_preparation.py    B  prepare(): reset, kontrola stanu, flush
  state_checker.py           B  stan bazy vs wzorzec
  plan_collector.py          B  plany wykonania
  wyniki/                    pomiary.csv, raport.md
```

## Zasady kodu

- Kod, nazwy i komentarze po angielsku, dokumentacja po polsku.
- Jedna klasa to jeden plik z jedną odpowiedzialnością, tak jak w C#.
- Kod ma być prosty do czytania: bez sztuczek Pythona i bez zbędnych abstrakcji.
- Każdy krok to osobny commit, np. `Krok 3: zapis wyników do CSV`.

## Uruchomienie

```bash
docker compose up -d                       # baza musi działać
.venv/bin/pip install -r requirements.txt  # sterownik oracledb (dopisujemy w kroku 1)
.venv/bin/python -m app.main               # z katalogu głównego projektu
```

## Rzeczy, które już wiemy (z prób)

- **T1 trwa ok. 2 min, T6 ok. 30 s, reszta po 1–3 s.** Pełna próbka to ok. 2,5–3 min, a seria 5 przebiegów z resetami ok. 15 min.
- **Reset bazy naszymi skryptami trwa ok. 15 s** i daje identyczne dane (to samo CSV).
- **Przy wczytywaniu `tN.sql` nie wolno wycinać linii zaczynających się od `SET`.** `SET TIMING ON` to polecenie SQL*Plus i trzeba je pominąć, ale w `t5.sql` linia `SET l.CenaDetaliczna = ...` jest częścią UPDATE. Pomijamy tylko polecenia SQL*Plus: `SET TIMING`, `SET LINESIZE`, `SET PAGESIZE`.
- **Instrukcje w plikach kończą się `;`, ale do Oracle wysyłamy je bez średnika.**
- **T4–T6 kończą się `ROLLBACK`.** Dane się nie zmieniają, ale sekwencje ID tak, dlatego potrzebny jest reset (krok 5).
- **Czas transakcji nie obejmuje końcowego `ROLLBACK`** (2–15 ms). Prawdziwa aplikacja kończyłaby transakcję przez COMMIT, a ROLLBACK służy tylko do przywrócenia danych po teście. Aplikacja wypisuje go z dopiskiem `(not counted)`.
- **Bez kroków B kolejne przebiegi się różnią.** Przykład z testu T5: przebieg 1 trwał 1317 ms, przebieg 2 985 ms, bo dane były już w pamięci. To pokazuje, po co jest `prepare()`.
- **Do flush i `V$SQL` potrzebny jest SYSTEM** (`ORACLE_PASSWORD` z `.env`). Transakcje wykonuje użytkownik APTEKA.
- **Tabele nie mają statystyk optymalizatora**, a nocne zadanie Oracle może je zebrać i zmienić plany. Dlatego jest krok 6.
- **Zapytania używają `SYSDATE`.** Wyniki na zajęciach mogą się trochę różnić od dzisiejszych, bo okno dat się przesuwa.
