"""Weryfikacja danych z data/przygotowane/: spojnosc oraz warunki transakcji T1-T6.

    .venv/bin/python tools/weryfikuj_dane.py

Skrypt tylko czyta pliki CSV i wypisuje wyniki kontroli.
"""
import csv
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

csv.field_size_limit(sys.maxsize)
SRC = Path(__file__).resolve().parent.parent / 'data' / 'przygotowane'
DATA_TESTOWA = date(2026, 10, 25)
OSTATNI_ROK = DATA_TESTOWA - timedelta(days=365)
OSTATNIE_3_LATA = DATA_TESTOWA - timedelta(days=3 * 365)
OSTATNIE_6_MIES = DATA_TESTOWA - timedelta(days=182)
AKTYWNE = {'NOWE', 'ZATWIERDZONE', 'W_REALIZACJI'}
ATC_BOL_GLOWY = ('N02B', 'N02C', 'M01AE')

bledy = []


def read(name):
    with open(SRC / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def d(s):
    return date.fromisoformat(s[:10])


def grosze(s):
    return round(float(s) * 100)


def sprawdz(opis, liczba_bledow, przyklad=None):
    status = 'OK ' if liczba_bledow == 0 else 'BLAD'
    print(f'  [{status}] {opis}: {liczba_bledow}' + (f'  np. {przyklad}' if liczba_bledow and przyklad else ''))
    if liczba_bledow:
        bledy.append(opis)


print('Wczytywanie...')
lek = {r['ID']: r for r in read('lek.csv')}
dost = {r['ID']: r for r in read('dostawca.csv')}
zam = {r['ID']: r for r in read('zamowienie.csv')}
pzam = read('pozycjazamowienia.csv')
sprz = {r['ID']: r for r in read('sprzedaz.csv')}
psprz = read('pozycjasprzedazy.csv')
atc = {k: (v['OpisLeku'].split('(ATC ')[1].split(')')[0] if '(ATC ' in v['OpisLeku'] else '') for k, v in lek.items()}
print(f'  Zamowienie={len(zam)} PozycjaZamowienia={len(pzam)} Sprzedaz={len(sprz)} PozycjaSprzedazy={len(psprz)}')

# ------------------------------------------------------------------ spojnosc
print('\n== Integralnosc i unikalnosc')
sprawdz('Zamowienie -> nieistniejacy dostawca', sum(z['DostawcaID'] not in dost for z in zam.values()))
sprawdz('PozycjaZamowienia -> nieistniejace zamowienie/lek',
        sum(p['ZamowienieID'] not in zam or p['LekID'] not in lek for p in pzam))
sprawdz('PozycjaSprzedazy -> nieistniejaca sprzedaz/lek',
        sum(p['SprzedazID'] not in sprz or p['LekID'] not in lek for p in psprz))
sprawdz('zamowienia bez pozycji', len(set(zam) - {p['ZamowienieID'] for p in pzam}))
sprawdz('paragony bez pozycji', len(set(sprz) - {p['SprzedazID'] for p in psprz}))
for nazwa, wiersze, kol, dl in (('KodZamowienia', zam.values(), 'KodZamowienia', 10),
                                ('KodPozycji zamowienia', pzam, 'KodPozycji', 8),
                                ('NumerParagonu', sprz.values(), 'NumerParagonu', 30),
                                ('KodPozycji sprzedazy', psprz, 'KodPozycji', 8)):
    w = list(wiersze)
    sprawdz(f'{nazwa}: duplikaty', len(w) - len({r[kol] for r in w}))
    sprawdz(f'{nazwa}: dluzsze niz {dl} znakow', sum(len(r[kol]) > dl for r in w))

print('\n== Wartosci i ceny')
suma_zam = defaultdict(int)
for p in pzam:
    suma_zam[p['ZamowienieID']] += int(p['Ilosc']) * grosze(p['CenaZakupu'])
sprawdz('WartoscZamowienia != suma pozycji', sum(grosze(z['WartoscZamowienia']) != suma_zam[k] for k, z in zam.items()))
suma_sprz = defaultdict(int)
for p in psprz:
    suma_sprz[p['SprzedazID']] += round(int(p['Ilosc']) * grosze(p['CenaSprzedazy']) * (100 - float(p['Rabat'])) / 100)
sprawdz('WartoscCalkowita != suma pozycji po rabacie',
        sum(abs(grosze(s['WartoscCalkowita']) - suma_sprz[k]) > 1 for k, s in sprz.items()))
sprawdz('CenaZakupu >= CenaDetaliczna', sum(grosze(p['CenaZakupu']) >= grosze(lek[p['LekID']]['CenaDetaliczna']) for p in pzam))

print('\n== Daty')
sprawdz('DataZamowienia przed umowa z dostawca',
        sum(d(z['DataZamowienia']) < d(dost[z['DostawcaID']]['DataPodpisaniaUmowy']) for z in zam.values()))
sprawdz('PlanowanaDostawa przed DataZamowienia', sum(d(z['PlanowanaDostawa']) < d(z['DataZamowienia']) for z in zam.values()))
sprawdz('zamowiony lek przed jego wprowadzeniem',
        sum(d(zam[p['ZamowienieID']]['DataZamowienia']) < d(lek[p['LekID']]['DataWprowadzenia']) for p in pzam))
sprawdz('DataDostarczenia przed DataZamowienia lub po dacie testowej',
        sum(p['DataDostarczenia'] != '' and not (d(zam[p['ZamowienieID']]['DataZamowienia']) <= d(p['DataDostarczenia']) <= DATA_TESTOWA) for p in pzam))
sprawdz('ZREALIZOWANE bez DataDostarczenia / inne z DataDostarczenia',
        sum((zam[p['ZamowienieID']]['Status'] == 'ZREALIZOWANE') != (p['DataDostarczenia'] != '') for p in pzam))
sprawdz('sprzedany lek przed jego wprowadzeniem',
        sum(d(sprz[p['SprzedazID']]['DataSprzedazy']) < d(lek[p['LekID']]['DataWprowadzenia']) for p in psprz))
sprawdz('DataUjecia != dzien sprzedazy', sum(p['DataUjecia'] != sprz[p['SprzedazID']]['DataSprzedazy'][:10] for p in psprz))
sprawdz('sprzedaz poza 2020-01-01..data testowa',
        sum(not (date(2020, 1, 1) <= d(s['DataSprzedazy']) <= DATA_TESTOWA) for s in sprz.values()))

# ------------------------------------------------------------------ rozklady
print('\n== Rozklady')
print('  statusy zamowien:', dict(Counter(z['Status'] for z in zam.values())))
print('  platnosci:', dict(Counter(s['SposobPlatnosci'] for s in sprz.values())))
print('  rabaty:', dict(Counter(p['Rabat'] for p in psprz)))
print('  godziny sprzedazy:', min(s['DataSprzedazy'][11:13] for s in sprz.values()), '-',
      max(s['DataSprzedazy'][11:13] for s in sprz.values()))
print('  sprzedaz wg roku:', dict(sorted(Counter(s['DataSprzedazy'][:4] for s in sprz.values()).items())))

opak_rok, opak_all, ost_sprz = Counter(), Counter(), {}
for p in psprz:
    dt = d(sprz[p['SprzedazID']]['DataSprzedazy'])
    opak_all[p['LekID']] += int(p['Ilosc'])
    if dt >= OSTATNI_ROK:
        opak_rok[p['LekID']] += int(p['Ilosc'])
    ost_sprz[p['LekID']] = max(ost_sprz.get(p['LekID'], dt), dt)
v = sorted(opak_all.values(), reverse=True)
top20 = sum(v[:len(lek) // 5]) / sum(v)
print(f'  opakowan na lek (cala historia): mediana={statistics.median(v)} max={v[0]}; '
      f'top 20% lekow = {top20:.0%} sprzedazy (rozklad Pareto ~80%)')
r = sorted((opak_rok.get(k, 0) for k in lek), reverse=True)
print(f'  opakowan na lek w ostatnich 12 mies.: mediana={statistics.median(r)} max={r[0]}')

# ------------------------------------------------------------------ T1-T6
print('\n== Warunki transakcji T1-T6')
staly = {k for k, x in dost.items() if d(x['DataPodpisaniaUmowy']) <= DATA_TESTOWA - timedelta(days=5 * 365)}
staz3 = {k for k, x in dost.items() if d(x['DataPodpisaniaUmowy']) <= DATA_TESTOWA - timedelta(days=3 * 365)}
zam_t1 = {p['LekID'] for p in pzam
          if zam[p['ZamowienieID']]['DostawcaID'] in staly and d(zam[p['ZamowienieID']]['DataZamowienia']) >= OSTATNIE_3_LATA
          and grosze(p['CenaZakupu']) < grosze(lek[p['LekID']]['CenaDetaliczna'])}
bol = {k for k in lek if atc[k].startswith(ATC_BOL_GLOWY)}
t1 = [k for k in bol if opak_rok[k] >= 100 and k in zam_t1]
print(f'  T1: leki na bol glowy z >=100 opak./12 mies. i zakupem u stalego dostawcy: {len(t1)} (z {len(bol)})')
print(f'  T3: leki powyzej sredniej sprzedazy: {sum(x > statistics.mean(opak_all.values()) for x in opak_all.values())}')
aktywne = {p['LekID'] for p in pzam if zam[p['ZamowienieID']]['Status'] in AKTYWNE}
t4 = [k for k in lek if opak_rok[k] >= 300 and k not in aktywne]
print(f'  T4: leki z >=300 opak./12 mies. bez aktywnego zamowienia: {len(t4)}; '
      f'dostawcy ze stazem >=3 lata: {len(staz3)}; leki w aktywnych zamowieniach: {len(aktywne)}')
# T5: srednia cena zakupu z ostatnich 6 miesiecy vs. poprzednie 6 miesiecy (zrealizowane zamowienia)
cena_6m, cena_wczesniej = defaultdict(list), defaultdict(list)
for p in pzam:
    z = zam[p['ZamowienieID']]
    dz = d(z['DataZamowienia'])
    if z['Status'] != 'ZREALIZOWANE' or dz < OSTATNI_ROK:
        continue
    (cena_6m if dz >= OSTATNIE_6_MIES else cena_wczesniej)[p['LekID']].append(grosze(p['CenaZakupu']))
wzrost = [k for k in cena_6m if k in cena_wczesniej
          and statistics.mean(cena_6m[k]) >= 1.10 * statistics.mean(cena_wczesniej[k])]
print(f'  T5: leki ze wzrostem sr. ceny zakupu >=10%: {len(wzrost)}, '
      f'z tego ze sprzedaza >100 opak./12 mies.: {sum(opak_rok[k] > 100 for k in wzrost)}; '
      f'leki o niezmiennej cenie zakupu: {sum(len(set(cena_6m[k] + cena_wczesniej[k])) == 1 for k in set(cena_6m) | set(cena_wczesniej))}')
t6 = [k for k, dt in ost_sprz.items() if dt < OSTATNIE_3_LATA and k not in aktywne]
print(f'  T6: leki sprzedawane, ale nie w ostatnich 3 latach i bez aktywnego zamowienia: {len(t6)} '
      f'(pozycji do usuniecia: {sum(p["LekID"] in set(t6) for p in psprz)})')

print('\n' + ('Wszystkie kontrole spojnosci OK.' if not bledy else f'Bledy spojnosci: {len(bledy)}'))
