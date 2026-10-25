"""Generuje syntetyczne zamowienia i sprzedaz dla przygotowanego katalogu.

Uruchom po tools/przygotuj_slowniki.py:
    python tools/generuj_transakcje.py

Wynik trafia do data/przygotowane/ i moze zostac zaladowany przez
tools/csv_do_sql.py. Generator jest deterministyczny (SEED).
"""
import argparse
import calendar
import csv
import random
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'przygotowane'
SEED = 42
DATA_TESTOWA = date(2026, 10, 25)
POCZATEK_HISTORII = date(2020, 1, 1)

# Mnozniki popytu dla miesiecy I–XII; 1.0 oznacza popyt bazowy.
# Konkretne wartosci mnoznikow sa syntetycznym przyblizeniem kierunku sezonu,
# bo publikacje udostepniaja dane kwartalne lub kategorie terapeutyczne,
# a nie pelne miesieczne szeregi dla kazdego produktu z katalogu.
# R06 i donosowe leki przeciwalergiczne: polska analiza apteczna pokazuje
# wzrost w II–III kwartale (Dudziński i in., Front. Pharmacol. 2025,
# https://doi.org/10.3389/fphar.2025.1649349).
# R05/R02 oraz R01BA: sezon infekcji/przeziebien zwykle XI–III
# (The Over-the-Counter Medicines Market in Poland, IJERPH 2022,
# https://doi.org/10.3390/ijerph192417022). J01 ma slabszy profil zimowy,
# bo sezon infekcji nie oznacza jednakowego wzrostu sprzedazy kazdego antybiotyku.
PROFIL_ALERGIA = (0.70, 0.80, 1.05, 1.40, 1.70, 1.75, 1.55, 1.25, 1.00, 0.80, 0.65, 0.65)
PROFIL_PRZEZIEBIENIE = (1.55, 1.45, 1.20, 0.85, 0.70, 0.60, 0.55, 0.60, 0.80, 1.15, 1.55, 1.75)
PROFIL_ANTYBIOTYK = (1.20, 1.15, 1.10, 1.00, 0.95, 0.95, 0.90, 0.90, 0.95, 1.05, 1.15, 1.20)
PROFIL_CALOROCZNY = (1.0,) * 12


def read_csv(name):
    with open(OUT / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def write_rows(name, header, rows):
    with open(OUT / name, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(header)
        writer.writerows(rows)


def cents(value):
    return int(round(float(value) * 100))


def money(value):
    return f'{value / 100:.2f}'


def random_day(rng, start, end):
    if start > end:
        start = end
    return start + timedelta(days=rng.randint(0, (end - start).days))


def profil_sezonowy(atc):
    """Zwraca miesieczny profil dla kodu ATC, bez zgadywania po nazwie handlowej."""
    if atc.startswith('R06') or atc.startswith(('R01AC', 'R01AD')):
        return PROFIL_ALERGIA
    if atc.startswith(('R05', 'R02', 'R01BA')):
        return PROFIL_PRZEZIEBIENIE
    if atc.startswith('J01'):
        return PROFIL_ANTYBIOTYK
    return PROFIL_CALOROCZNY


def losuj_date_sprzedazy(rng, profil, od):
    """Losuje date z uwzglednieniem dostepnosci produktu i miesiecznego popytu."""
    od = max(od, POCZATEK_HISTORII)
    miesiace, wagi = [], []
    for rok in range(od.year, DATA_TESTOWA.year + 1):
        for miesiac in range(1, 13):
            if (rok, miesiac) < (od.year, od.month) or (rok, miesiac) > (DATA_TESTOWA.year, DATA_TESTOWA.month):
                continue
            pierwszy = date(rok, miesiac, 1)
            poczatek = max(od, pierwszy)
            koniec_miesiaca = date(rok, miesiac, calendar.monthrange(rok, miesiac)[1])
            koniec = min(koniec_miesiaca, DATA_TESTOWA)
            dni = (koniec - poczatek).days + 1
            if dni > 0:
                miesiace.append((poczatek, dni))
                wagi.append(dni * profil[miesiac - 1])
    poczatek, dni = rng.choices(miesiace, weights=wagi, k=1)[0]
    return poczatek + timedelta(days=rng.randrange(dni))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pozycji-sprzedazy', type=int, default=1_000_000,
                        help='liczba pozycji sprzedaży (domyślnie 1000000; zakres docelowy 300000–1000000)')
    parser.add_argument('--zamowien', type=int, default=20_000,
                        help='liczba zamówień (domyślnie 20000; zakres docelowy 15000–30000)')
    parser.add_argument('--pozycji-zamowien', type=int, default=175_000,
                        help='liczba pozycji zamówień (domyślnie 175000; zakres docelowy 150000–200000)')
    args = parser.parse_args()
    if min(args.pozycji_sprzedazy, args.zamowien, args.pozycji_zamowien) <= 0:
        parser.error('liczby rekordów muszą być większe od zera')
    if args.pozycji_zamowien < args.zamowien:
        parser.error('musi być co najmniej jedna pozycja na każde zamówienie')

    rng = random.Random(SEED)
    leki_rows = read_csv('lek.csv')
    cena_rows = read_csv('lek_ceny.csv')
    dostawcy_rows = read_csv('dostawca.csv')
    meta_rows = read_csv('dostawca_meta.csv')
    ceny = {int(r['LekID']): cents(r['CenaHurtowaBrutto']) for r in cena_rows}
    leki = []
    for r in leki_rows:
        lid = int(r['ID'])
        m_atc = re.search(r'ATC\s+([A-Z0-9]+)', r['OpisLeku'])
        atc = m_atc.group(1) if m_atc else ''
        leki.append({'id': lid, 'od': date.fromisoformat(r['DataWprowadzenia']),
                     'detal': cents(r['CenaDetaliczna']), 'hurt': ceny[lid], 'atc': atc,
                     'profil': profil_sezonowy(atc)})
    leki = [l for l in leki if l['od'] <= DATA_TESTOWA]
    if not leki:
        raise ValueError('Brak leków dostępnych w okresie symulacji')

    # Zamówienia: data po podpisaniu umowy; plan i dostawa w logicznej kolejności.
    meta = {r['DostawcaID']: r for r in meta_rows}
    dostawcy = [r for r in dostawcy_rows if r['ID'] in meta]
    if not dostawcy:
        raise ValueError('Brak dostawców z metadanymi umów')
    zamowienia, pozycje_zam = [], []
    pozycje_na_zamowienie = [1] * args.zamowien
    for _ in range(args.pozycji_zamowien - args.zamowien):
        pozycje_na_zamowienie[rng.randrange(args.zamowien)] += 1

    for zam_id, liczba_pozycji in enumerate(pozycje_na_zamowienie, 1):
        dostawca = rng.choice(dostawcy)
        umowa = date.fromisoformat(dostawca['DataPodpisaniaUmowy'])
        dostawy = [(rng.choice(leki),
                    rng.choices((1, 2, 3, 5, 10, 20, 50), weights=(5, 10, 15, 25, 25, 15, 5))[0])
                   for _ in range(liczba_pozycji)]
        najwczesniejszy_zakup = max([umowa, POCZATEK_HISTORII] + [lek['od'] for lek, _ in dostawy])
        data_zam = random_day(rng, najwczesniejszy_zakup, DATA_TESTOWA - timedelta(days=8))
        plan = data_zam + timedelta(days=rng.randint(1, 5))
        dostawy_z_cenami = []
        for lek, ilosc in dostawy:
            data_przyj = max(plan, lek['od']) + timedelta(days=rng.randint(0, 2))
            cena = lek['hurt']
            dostawy_z_cenami.append((lek, ilosc, cena, data_przyj))
        wartosc = sum(ilosc * cena for _, ilosc, cena, _ in dostawy_z_cenami)
        status = 'ZREALIZOWANE'
        kod = f'Z{zam_id:09d}'
        zamowienia.append([zam_id, dostawca['ID'], data_zam.isoformat(), plan.isoformat(), status,
                           money(wartosc), kod])
        for poz_id, (lek, ilosc, cena, data_przyj) in enumerate(dostawy_z_cenami, len(pozycje_zam) + 1):
            pozycje_zam.append([poz_id, zam_id, lek['id'], ilosc, money(cena), data_przyj.isoformat(),
                                f'ZP{poz_id:06d}'])

    write_rows('zamowienie.csv', ['ID', 'DostawcaID', 'DataZamowienia', 'PlanowanaDostawa', 'Status',
                                  'WartoscZamowienia', 'KodZamowienia'], zamowienia)
    write_rows('pozycjazamowienia.csv', ['ID', 'ZamowienieID', 'LekID', 'Ilosc', 'CenaZakupu',
                                         'DataDostarczenia', 'KodPozycji'], pozycje_zam)

    # Sprzedaż: dokładna liczba pozycji, średnio dwie pozycje na paragon.
    paragon_count = max(1, round(args.pozycji_sprzedazy / 2.0))
    pozycje_na_paragon = [1] * paragon_count
    for _ in range(args.pozycji_sprzedazy - paragon_count):
        pozycje_na_paragon[rng.randrange(paragon_count)] += 1
    sprzedaze, pozycje_sprz = [], []
    platnosci = ('GOTOWKA', 'KARTA', 'BLIK')
    kasy = ('K001', 'K002', 'K003', 'K004')
    for sprz_id, liczba_pozycji in enumerate(pozycje_na_paragon, 1):
        linie = []
        for _ in range(liczba_pozycji):
            lek = rng.choice(leki)
            ilosc = rng.choices((1, 2, 3, 4, 5), weights=(70, 20, 6, 3, 1))[0]
            rabat = rng.choices((0, 5, 10, 15), weights=(80, 10, 8, 2))[0]
            cena = lek['detal']
            linie.append((lek, ilosc, cena, rabat))
        # Pozycje paragonu mają wspólną datę i sezonowość odpowiadającą
        # głównej grupie ATC na paragonie.
        profil = tuple(sum(lek['profil'][i] for lek, _, _, _ in linie) / len(linie) for i in range(12))
        data_sprz = losuj_date_sprzedazy(rng, profil, max(lek['od'] for lek, _, _, _ in linie))
        wartosc = 0
        for poz_id, (lek, ilosc, cena, rabat) in enumerate(linie, len(pozycje_sprz) + 1):
            wartosc += round(ilosc * cena * (100 - rabat) / 100)
            pozycje_sprz.append([poz_id, sprz_id, lek['id'], ilosc, money(cena), rabat,
                                 data_sprz.isoformat(), f'S{poz_id:07d}'])
        sprzedaze.append([sprz_id, datetime.combine(data_sprz, time(8 + rng.randrange(12),
                                                                     rng.randrange(60))).strftime('%Y-%m-%d %H:%M:%S'),
                          f'PAR{sprz_id:09d}', rng.choice(platnosci), money(wartosc), rng.choice(kasy)])

    write_rows('sprzedaz.csv', ['ID', 'DataSprzedazy', 'NumerParagonu', 'SposobPlatnosci',
                                'WartoscCalkowita', 'KodKasy'], sprzedaze)
    write_rows('pozycjasprzedazy.csv', ['ID', 'SprzedazID', 'LekID', 'Ilosc', 'CenaSprzedazy', 'Rabat',
                                        'DataUjecia', 'KodPozycji'], pozycje_sprz)

    print(f'Zamowienie: {len(zamowienia):,}; PozycjaZamowienia: {len(pozycje_zam):,}')
    print(f'Sprzedaz: {len(sprzedaze):,}; PozycjaSprzedazy: {len(pozycje_sprz):,}')
    print(f'Ceny zakupu pochodzą z lek_ceny.csv; pliki zapisano w {OUT.relative_to(ROOT)}/')


if __name__ == '__main__':
    main()
