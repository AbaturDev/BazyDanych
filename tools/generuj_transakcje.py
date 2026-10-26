"""Generuje syntetyczne zamowienia i sprzedaz dla przygotowanego katalogu.

Uruchom po tools/przygotuj_slowniki.py:
    python tools/generuj_transakcje.py

Wynik trafia do data/przygotowane/ i moze zostac zaladowany przez
tools/csv_do_sql.py. Generator jest deterministyczny (SEED).

Zalozenia symulacji (pod transakcje T1-T6 z etapu 2):
  * popularnosc lekow ma rozklad dlugoogonowy (log-normalny): ok. 20% lekow daje
    ok. 80% sprzedazy; leki bez recepty i przeciwbolowe sa czesciej kupowane,
  * sprzedaz rosnie o ok. 7% rocznie i ma sezonowosc (ogolna + wg grupy ATC),
  * ceny zakupu i sprzedazy rosna z inflacja (ok. 4,5% rocznie); dla czesci lekow
    hurtownie podniosly ceny zakupu o 12-25% ok. pol roku przed data testowa (T5),
  * zamowienia z ostatnich tygodni sa jeszcze aktywne (NOWE, ZATWIERDZONE,
    W_REALIZACJI), ok. 3% zamowien jest anulowanych (T4, T6),
  * czesc lekow zostala wycofana ze sprzedazy w latach 2021-2023: maja stara historie
    sprzedazy i zamowien, ale nic po dacie wycofania (T6).
"""
import argparse
import bisect
import calendar
import csv
import itertools
import math
import random
import re
import sys
from collections import Counter
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
# Ruch w aptece ogolem (liczba paragonow) - wiecej w sezonie infekcji
RUCH_MIESIECZNY = (1.10, 1.06, 1.02, 0.97, 0.95, 0.92, 0.90, 0.92, 0.98, 1.03, 1.07, 1.12)
WZROST_ROCZNY = 0.07          # organiczny wzrost liczby transakcji rok do roku
WPLYW_ASORTYMENTU = 0.8       # jak mocno liczba transakcji zalezy od wielkosci asortymentu
INFLACJA_ROCZNA = 0.045       # wzrost cen lekow rok do roku

# Popularnosc lekow: log-normalna; mnozniki wg kategorii dostepnosci i grupy
POPULARNOSC_SIGMA = 1.6
MNOZNIK_KATEGORII = {'OTC': 2.0, 'Rp': 1.0, 'Rpz': 0.3, 'Rpw': 0.4}
ATC_BOL_GLOWY = ('N02B', 'N02C', 'M01AE')
MNOZNIK_BOL_GLOWY = 2.5

# Scenariusze pod T5 i T6
UDZIAL_PODWYZEK = 0.08        # leki z podwyzka ceny zakupu (T5)
PODWYZKA = (0.12, 0.25)
PODWYZKA_DNI_PRZED = (183, 200)   # tuz przed oknem "ostatnich 6 miesiecy"
UDZIAL_WYCOFANYCH = 0.04      # leki wycofane ze sprzedazy (T6)
WYCOFANIE_OD, WYCOFANIE_DO = date(2021, 3, 1), date(2023, 9, 30)
WAHANIE_CENY_ZAKUPU = 0.05    # +-5% miedzy dostawami
MAKS_ZAKUP_DO_DETALU = 0.97   # cena zakupu zawsze ponizej ceny sprzedazy

# Statusy zamowien wg wieku zamowienia (dni od zlozenia do daty testowej)
UDZIAL_ANULOWANYCH = 0.03


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


def profil_sezonowy(atc):
    """Zwraca miesieczny profil dla kodu ATC, bez zgadywania po nazwie handlowej."""
    if atc.startswith('R06') or atc.startswith(('R01AC', 'R01AD')):
        return PROFIL_ALERGIA
    if atc.startswith(('R05', 'R02', 'R01BA')):
        return PROFIL_PRZEZIEBIENIE
    if atc.startswith('J01'):
        return PROFIL_ANTYBIOTYK
    return PROFIL_CALOROCZNY


def indeks_cen(dzien):
    """Poziom cen wzgledem daty testowej (1.0 = ceny z tabeli Lek); stały w obrebie miesiaca."""
    lata = (date(dzien.year, dzien.month, 15) - DATA_TESTOWA).days / 365.25
    return (1 + INFLACJA_ROCZNA) ** lata


def miesiace_historii():
    """Miesiace symulacji: (pierwszy dzien, ostatni dzien, waga ruchu)."""
    out = []
    for rok, mies in itertools.product(range(POCZATEK_HISTORII.year, DATA_TESTOWA.year + 1), range(1, 13)):
        start = date(rok, mies, 1)
        if start > DATA_TESTOWA:
            break
        koniec = min(date(rok, mies, calendar.monthrange(rok, mies)[1]), DATA_TESTOWA)
        lata = (start - POCZATEK_HISTORII).days / 365.25
        waga = ((koniec - start).days + 1) * RUCH_MIESIECZNY[mies - 1] * (1 + WZROST_ROCZNY) ** lata
        out.append((start, koniec, waga))
    return out


class Asortyment:
    """Losowanie lekow dostepnych w danym miesiacu, z wagami popularnosci i sezonu."""

    def __init__(self, leki, miesiace, sezon):
        self.koszyki = []
        for start, koniec, _ in miesiace:
            dostepne = [l for l in leki if l['od'] <= koniec and (l['do'] is None or l['do'] >= start)]
            wagi = [l['pop'] * (l['profil'][start.month - 1] if sezon else 1.0) for l in dostepne]
            self.koszyki.append((dostepne, list(itertools.accumulate(wagi))))

    def losuj(self, rng, i_mies, dzien, k=1, bez_powtorzen=False):
        dostepne, cum = self.koszyki[i_mies]
        wynik, uzyte = [], set()
        for _ in range(k * 50):
            lek = rng.choices(dostepne, cum_weights=cum)[0]
            if dzien < lek['od'] or (lek['do'] is not None and dzien > lek['do']):
                continue
            if bez_powtorzen and lek['id'] in uzyte:
                continue
            uzyte.add(lek['id'])
            wynik.append(lek)
            if len(wynik) == k:
                break
        if len(wynik) < k:
            # np. pierwsze dni po uruchomieniu systemu: dostepna jest tylko czesc asortymentu miesiaca
            reszta = [l for l in dostepne if l['od'] <= dzien and (l['do'] is None or dzien <= l['do'])
                      and not (bez_powtorzen and l['id'] in uzyte)]
            while len(wynik) < k and reszta:
                lek = rng.choice(reszta)
                if bez_powtorzen:
                    reszta.remove(lek)
                    uzyte.add(lek['id'])
                wynik.append(lek)
        return wynik

    def udzial_popularnosci(self, i_mies, suma_wszystkich):
        """Jaka czesc popytu calego katalogu jest dostepna w danym miesiacu (0..1)."""
        dostepne, _ = self.koszyki[i_mies]
        return sum(l['pop'] for l in dostepne) / suma_wszystkich


def status_zamowienia(rng, wiek):
    if wiek > 3 and rng.random() < UDZIAL_ANULOWANYCH:
        return 'ANULOWANE'
    if wiek <= 3:
        return 'NOWE'
    if wiek <= 10:
        return rng.choice(('ZATWIERDZONE', 'W_REALIZACJI'))
    if wiek <= 21:
        return 'W_REALIZACJI' if rng.random() < 0.3 else 'ZREALIZOWANE'
    return 'ZREALIZOWANE'


def cena_zakupu(rng, lek, dzien):
    cena = lek['hurt'] * indeks_cen(dzien)
    if lek['podwyzka_od'] and dzien >= lek['podwyzka_od']:
        cena *= 1 + lek['podwyzka']
    cena *= rng.uniform(1 - WAHANIE_CENY_ZAKUPU, 1 + WAHANIE_CENY_ZAKUPU)
    cena = min(cena, MAKS_ZAKUP_DO_DETALU * lek['detal'] * indeks_cen(dzien))
    return max(1, round(cena))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
    ceny = {int(r['LekID']): (cents(r['CenaHurtowaBrutto']), r['Kategoria']) for r in read_csv('lek_ceny.csv')}

    # ---------------------------------------------------------------- leki i scenariusze
    leki = []
    for r in read_csv('lek.csv'):
        lid = int(r['ID'])
        m_atc = re.search(r'ATC\s+([A-Z0-9]+)', r['OpisLeku'])
        atc = m_atc.group(1) if m_atc else ''
        hurt, kat = ceny[lid]
        pop = math.exp(rng.gauss(0, POPULARNOSC_SIGMA)) * MNOZNIK_KATEGORII.get(kat, 1.0)
        if atc.startswith(ATC_BOL_GLOWY):
            pop *= MNOZNIK_BOL_GLOWY
        leki.append({'id': lid, 'od': max(date.fromisoformat(r['DataWprowadzenia']), POCZATEK_HISTORII),
                     'do': None, 'detal': cents(r['CenaDetaliczna']), 'hurt': hurt, 'atc': atc,
                     'profil': profil_sezonowy(atc), 'pop': pop, 'podwyzka_od': None, 'podwyzka': 0.0})
    leki = [l for l in leki if l['od'] <= DATA_TESTOWA]

    # T6: wycofane leki - tylko takie, ktore byly w sprzedazy przynajmniej rok przed wycofaniem
    kandydaci = [l for l in leki if l['od'] <= WYCOFANIE_OD - timedelta(days=365)]
    for lek in rng.sample(kandydaci, round(UDZIAL_WYCOFANYCH * len(leki))):
        lek['do'] = WYCOFANIE_OD + timedelta(days=rng.randint(0, (WYCOFANIE_DO - WYCOFANIE_OD).days))
    # T5: podwyzki cen zakupu (tylko leki nadal sprzedawane)
    aktywne_leki = [l for l in leki if l['do'] is None]
    for lek in rng.sample(aktywne_leki, round(UDZIAL_PODWYZEK * len(leki))):
        lek['podwyzka_od'] = DATA_TESTOWA - timedelta(days=rng.randint(*PODWYZKA_DNI_PRZED))
        lek['podwyzka'] = rng.uniform(*PODWYZKA)

    miesiace = miesiace_historii()
    asort_sprzedaz = Asortyment(leki, miesiace, sezon=True)
    # Ruch w aptece rosnie organicznie (WZROST_ROCZNY) oraz razem z poszerzaniem asortymentu:
    # im wiecej (popularnych) lekow w ofercie, tym wiecej klientow i zamowien.
    suma_pop = sum(l['pop'] for l in leki)
    wagi = [m[2] * asort_sprzedaz.udzial_popularnosci(i, suma_pop) ** WPLYW_ASORTYMENTU
            for i, m in enumerate(miesiace)]
    wagi_miesiecy = list(itertools.accumulate(wagi))

    def losuj_dzien():
        i = rng.choices(range(len(miesiace)), cum_weights=wagi_miesiecy)[0]
        start, koniec, _ = miesiace[i]
        return i, start + timedelta(days=rng.randint(0, (koniec - start).days))

    # ---------------------------------------------------------------- zamowienia
    # Apteka zamawia glownie u kilku duzych hurtowni - popularnosc dostawcow tez jest nierowna.
    dostawcy = sorted(read_csv('dostawca.csv'), key=lambda r: r['DataPodpisaniaUmowy'])
    umowy = [date.fromisoformat(r['DataPodpisaniaUmowy']) for r in dostawcy]
    cum_dost = list(itertools.accumulate(math.exp(rng.gauss(0, 1.0)) for _ in dostawcy))

    zamowienia, pozycje_zam = [], []
    pozycje_na_zamowienie = [1] * args.zamowien
    for _ in range(args.pozycji_zamowien - args.zamowien):
        pozycje_na_zamowienie[rng.randrange(args.zamowien)] += 1

    plan = []
    for liczba in pozycje_na_zamowienie:
        i_mies, dzien = losuj_dzien()
        plan.append((dzien, i_mies, liczba))
    plan.sort(key=lambda x: x[0])   # ID zamowien rosna z data

    for zam_id, (data_zam, i_mies, liczba_pozycji) in enumerate(plan, 1):
        k = bisect.bisect_right(umowy, data_zam)
        dostawca = rng.choices(dostawcy[:k], cum_weights=cum_dost[:k])[0]
        wiek = (DATA_TESTOWA - data_zam).days
        status = status_zamowienia(rng, wiek)
        planowana = data_zam + timedelta(days=rng.randint(1, 5))
        linie = asort_sprzedaz.losuj(rng, i_mies, data_zam, k=liczba_pozycji, bez_powtorzen=True)
        wartosc = 0
        for lek in linie:
            ilosc = rng.choices((1, 2, 3, 5, 10, 20, 50), weights=(5, 10, 15, 25, 25, 15, 5))[0]
            cena = cena_zakupu(rng, lek, data_zam)
            dostarczono = ''
            if status == 'ZREALIZOWANE':
                dostarczono = min(planowana + timedelta(days=rng.randint(0, 2)), DATA_TESTOWA).isoformat()
            wartosc += ilosc * cena
            poz_id = len(pozycje_zam) + 1
            pozycje_zam.append([poz_id, zam_id, lek['id'], ilosc, money(cena), dostarczono, f'ZP{poz_id:06d}'])
        zamowienia.append([zam_id, dostawca['ID'], data_zam.isoformat(), planowana.isoformat(), status,
                           money(wartosc), f'Z{zam_id:09d}'])

    write_rows('zamowienie.csv', ['ID', 'DostawcaID', 'DataZamowienia', 'PlanowanaDostawa', 'Status',
                                  'WartoscZamowienia', 'KodZamowienia'], zamowienia)
    write_rows('pozycjazamowienia.csv', ['ID', 'ZamowienieID', 'LekID', 'Ilosc', 'CenaZakupu',
                                         'DataDostarczenia', 'KodPozycji'], pozycje_zam)

    # ---------------------------------------------------------------- sprzedaz
    # Dokładna liczba pozycji, średnio dwie pozycje na paragon.
    paragon_count = max(1, round(args.pozycji_sprzedazy / 2.0))
    pozycje_na_paragon = [1] * paragon_count
    for _ in range(args.pozycji_sprzedazy - paragon_count):
        pozycje_na_paragon[rng.randrange(paragon_count)] += 1

    paragony = []
    for liczba in pozycje_na_paragon:
        i_mies, dzien = losuj_dzien()
        godzina = time(8 + rng.choices(range(12), weights=(4, 6, 7, 7, 7, 7, 8, 9, 10, 9, 7, 4))[0],
                       rng.randrange(60))
        paragony.append((datetime.combine(dzien, godzina), i_mies, liczba))
    paragony.sort(key=lambda x: x[0])   # numery paragonow rosna z czasem

    sprzedaze, pozycje_sprz = [], []
    platnosci = ('GOTOWKA', 'KARTA', 'BLIK')
    kasy = ('K001', 'K002', 'K003', 'K004')
    for sprz_id, (kiedy, i_mies, liczba_pozycji) in enumerate(paragony, 1):
        dzien = kiedy.date()
        # udzial platnosci gotowka spada z roku na rok na rzecz karty i BLIK
        rok = dzien.year - POCZATEK_HISTORII.year
        platnosc = rng.choices(platnosci, weights=(max(45 - 5 * rok, 15), 45, 10 + 5 * rok))[0]
        wartosc = 0
        for lek in asort_sprzedaz.losuj(rng, i_mies, dzien, k=liczba_pozycji):
            ilosc = rng.choices((1, 2, 3, 4, 5), weights=(70, 20, 6, 3, 1))[0]
            rabat = rng.choices((0, 5, 10, 15), weights=(80, 10, 8, 2))[0]
            cena = max(1, round(lek['detal'] * indeks_cen(dzien)))
            wartosc += round(ilosc * cena * (100 - rabat) / 100)
            poz_id = len(pozycje_sprz) + 1
            pozycje_sprz.append([poz_id, sprz_id, lek['id'], ilosc, money(cena), rabat,
                                 dzien.isoformat(), f'S{poz_id:07d}'])
        sprzedaze.append([sprz_id, kiedy.strftime('%Y-%m-%d %H:%M:%S'), f'PAR{sprz_id:09d}', platnosc,
                          money(wartosc), rng.choice(kasy)])

    write_rows('sprzedaz.csv', ['ID', 'DataSprzedazy', 'NumerParagonu', 'SposobPlatnosci',
                                'WartoscCalkowita', 'KodKasy'], sprzedaze)
    write_rows('pozycjasprzedazy.csv', ['ID', 'SprzedazID', 'LekID', 'Ilosc', 'CenaSprzedazy', 'Rabat',
                                        'DataUjecia', 'KodPozycji'], pozycje_sprz)

    print(f'Zamowienie: {len(zamowienia):,}; PozycjaZamowienia: {len(pozycje_zam):,}')
    print(f'  statusy: {dict(Counter(z[4] for z in zamowienia))}')
    print(f'Sprzedaz: {len(sprzedaze):,}; PozycjaSprzedazy: {len(pozycje_sprz):,}')
    print(f'Scenariusze: wycofane leki (T6) = {sum(l["do"] is not None for l in leki)}, '
          f'podwyzki cen zakupu (T5) = {sum(l["podwyzka_od"] is not None for l in leki)}')
    print(f'Pliki zapisano w {OUT.relative_to(ROOT)}/')


if __name__ == '__main__':
    main()
