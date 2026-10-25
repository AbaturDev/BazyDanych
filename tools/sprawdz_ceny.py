"""Szybka kontrola cen w data/przygotowane/: python tools/sprawdz_ceny.py"""
import collections
import csv
import statistics
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'data' / 'przygotowane'


def read(name):
    with open(OUT / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


lek = {r['ID']: r for r in read('lek.csv')}
ceny = read('lek_ceny.csv')

groups = collections.defaultdict(list)
for c in ceny:
    groups[(c['Kategoria'], c['ZrodloCeny'])].append(float(c['CenaDetaliczna']))
for (kat, zrodlo), v in sorted(groups.items()):
    v.sort()
    print(f'{kat:4} {zrodlo:28} n={len(v):5} min={v[0]:8.2f} mediana={statistics.median(v):8.2f} '
          f'max={v[-1]:8.2f} rozne_ceny={len(set(v))}')

print('cena hurtowa >= detaliczna:', sum(float(c['CenaHurtowaBrutto']) >= float(c['CenaDetaliczna']) for c in ceny))
print('przyklady:')
for prefix in ('Apap', 'Ibuprom', 'Nurofen', 'Paracetamol', 'Polopiryna', 'Sumamigren'):
    for c in [c for c in ceny if lek[c['LekID']]['Nazwa'].startswith(prefix)][:2]:
        print(f"  {lek[c['LekID']]['Nazwa'][:60]:60} {c['CenaDetaliczna']:>8} zl  {c['ZrodloCeny']}")
