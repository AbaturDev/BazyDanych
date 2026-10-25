"""Przygotowanie danych slownikowych: Producent, Lek, Dostawca.

Zrodla (katalog data/):
  * leki.csv                               - Rejestr Produktow Leczniczych (URPL),
  * hurtownie.csv                          - Rejestr Hurtowni Farmaceutycznych (GIF),
  * obwieszczenie.xlsx                     - wykaz lekow refundowanych MZ na 1.10.2026
                                             (urzedowe ceny hurtowe i detaliczne).

Wynik (katalog data/przygotowane/):
  * producent.csv, lek.csv, dostawca.csv - kolumny zgodne z db/scripts/schema.sql,
  * lek_ceny.csv      - cena hurtowa + zrodlo ceny (dla generatora zamowien, nie trafia do bazy),
  * dostawca_meta.csv - daty zezwolenia hurtowni (dla generatora zamowien, nie trafia do bazy).

Uruchomienie z katalogu projektu (wymaga openpyxl, patrz requirements.txt):
    .venv/bin/python tools/przygotuj_slowniki.py

Asortyment: LICZBA_LEKOW opakowan; dostawcy - wszystkie pasujace hurtownie;
producenci - wszyscy wytworcy wybranych lekow.

Co jest prawdziwe, a co syntetyczne:
  * prawdziwe: nazwy lekow, moc, postac, opakowanie, EAN, ATC, kategoria dostepnosci,
    wytworca i kraj (RPL); nazwy firm, NIP i daty zezwolen hurtowni (GIF);
    ceny detaliczne i hurtowe lekow refundowanych (obwieszczenie MZ);
  * szacowane: ceny lekow spoza obwieszczenia - z ceny jednostkowej tej samej substancji
    i dawki z obwieszczenia (kolejne poziomy zastepcze opisane w szacuj_cene);
  * syntetyczne: daty wprowadzenia lekow, daty wspolpracy/umow, telefony dostawcow.
Generator jest deterministyczny - to samo ziarno daje te same pliki.
"""
import csv
import math
import random
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

csv.field_size_limit(sys.maxsize)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
OUT = DATA / 'przygotowane'
OBWIESZCZENIE = DATA / 'obwieszczenie.xlsx'

LICZBA_LEKOW = 8000
SEED = 42

# Data odniesienia calej symulacji (etap 2: "ostatnie 12 miesiecy", "3 lata", "5 lat")
DATA_TESTOWA = date(2026, 10, 25)
POCZATEK_HISTORII = date(2020, 1, 1)

# Apteka ogolnodostepna: bez lekow szpitalnych (Lz) i skasowanych opakowan
KATEGORIE_APTECZNE = {'OTC', 'Rp', 'Rpz', 'Rpw'}
OPIS_KATEGORII = {
    'OTC': 'lek wydawany bez recepty',
    'Rp': 'lek wydawany na recepte',
    'Rpz': 'lek wydawany na recepte do zastrzezonego stosowania',
    'Rpw': 'lek zawierajacy substancje psychotropowe lub odurzajace, wydawany na recepte',
}

# Sklad asortymentu
ATC_BOL_GLOWY = ('N02B', 'N02C', 'M01AE')   # T1: leki na bol glowy / migrene
LIMIT_BOL_GLOWY = 500
LIMIT_REFUNDOWANE = 2500                    # leki z prawdziwa cena z obwieszczenia

# Szacowanie cen spoza obwieszczenia (zalozenia, do skalibrowania na kilkunastu cenach rynkowych):
# ceny urzedowe lekow refundowanych sa nizsze niz ceny wolnorynkowe tych samych substancji.
NARZUT_RX_NIEREFUNDOWANY = 1.15
NARZUT_OTC = 1.60
CENA_MIN, CENA_MAX_SZACUNEK = 3.00, 1500.00   # ceny z obwieszczenia nie sa obcinane
CENA_MAX_OTC = 300.00                          # leki bez recepty prawie nigdy nie kosztuja wiecej

# Grupy stazu dostawcow wzgledem DATA_TESTOWA (T1: >= 5 lat, T4: >= 3 lata) i ich udzial
GRUPY_DOSTAWCOW = [
    ('>=5 lat', 0.40, date(2010, 1, 1), date(2021, 10, 24)),
    ('3-5 lat', 0.25, date(2021, 10, 25), date(2023, 10, 24)),
    ('<3 lata', 0.35, date(2023, 10, 25), date(2026, 9, 30)),
]
# Hurtownia zamknieta przed tym dniem nie moglaby nic dostarczyc w analizowanym okresie
MIN_KONIEC_ZEZWOLENIA = date(2021, 1, 1)

KIERUNKOWE = {
    'mazowieckie': '22', 'małopolskie': '12', 'śląskie': '32', 'dolnośląskie': '71',
    'wielkopolskie': '61', 'łódzkie': '42', 'pomorskie': '58', 'kujawsko-pomorskie': '52',
    'lubelskie': '81', 'podkarpackie': '17', 'zachodniopomorskie': '91', 'warmińsko-mazurskie': '89',
    'podlaskie': '85', 'świętokrzyskie': '41', 'opolskie': '77', 'lubuskie': '68',
}

# Opisy grup ATC (od najbardziej szczegolowych) - trafiaja do OpisLeku
OPIS_ATC = [
    ('N02C', 'lek przeciwmigrenowy, stosowany w leczeniu napadow migreny i bolu glowy'),
    ('N02BE', 'lek przeciwbolowy i przeciwgoraczkowy (anilidy, np. paracetamol), stosowany przy bolu glowy, '
              'migrenie, bolu zebow, bolach miesniowych i goraczce'),
    ('N02BB', 'lek przeciwbolowy i przeciwgoraczkowy (pirazolony, np. metamizol), stosowany przy silnym bolu, '
              'bolu glowy i goraczce'),
    ('N02BA', 'lek przeciwbolowy (kwas acetylosalicylowy i pochodne), stosowany przy bolu glowy, migrenie i goraczce'),
    ('N02B', 'lek przeciwbolowy i przeciwgoraczkowy, stosowany przy bolu glowy i migrenie'),
    ('N02A', 'opioidowy lek przeciwbolowy, stosowany w silnym bolu'),
    ('M01AE', 'niesteroidowy lek przeciwzapalny (pochodne kwasu propionowego, np. ibuprofen, naproksen, ketoprofen), '
              'stosowany przy bolu glowy, migrenie, bolach miesniowych, bolu zebow i goraczce'),
    ('M01A', 'niesteroidowy lek przeciwzapalny i przeciwreumatyczny, stosowany przy bolu i stanach zapalnych'),
    ('R05', 'lek stosowany w kaszlu i przeziebieniu'),
    ('R06', 'lek przeciwhistaminowy, stosowany w alergii'),
    ('R01', 'lek do stosowania donosowego, stosowany przy niezytach nosa'),
    ('R03', 'lek stosowany w chorobach obturacyjnych drog oddechowych (astma, POChP)'),
    ('A02', 'lek stosowany w zaburzeniach zwiazanych z nadkwasota i chorobie wrzodowej'),
    ('A07', 'lek przeciwbiegunkowy i przeciwzapalny dzialajacy w jelitach'),
    ('A10', 'lek stosowany w cukrzycy'),
    ('A11', 'preparat witaminowy'),
    ('A12', 'preparat mineralny'),
    ('B01', 'lek przeciwzakrzepowy'),
    ('C07', 'lek beta-adrenolityczny, stosowany w nadcisnieniu i chorobach serca'),
    ('C08', 'antagonista wapnia, stosowany w nadcisnieniu'),
    ('C09', 'lek dzialajacy na uklad renina-angiotensyna, stosowany w nadcisnieniu'),
    ('C10', 'lek zmniejszajacy stezenie lipidow (np. statyny)'),
    ('D', 'lek dermatologiczny'),
    ('G03', 'hormon plciowy lub modulator ukladu plciowego'),
    ('H', 'hormonalny lek do stosowania ogolnego'),
    ('J01', 'antybiotyk do stosowania ogolnego'),
    ('J', 'lek przeciwinfekcyjny do stosowania ogolnego'),
    ('L', 'lek przeciwnowotworowy lub immunomodulujacy'),
    ('N05', 'lek psycholeptyczny (przeciwpsychotyczny, przeciwlekowy lub nasenny)'),
    ('N06', 'lek psychoanaleptyczny (np. przeciwdepresyjny)'),
    ('N03', 'lek przeciwpadaczkowy'),
    ('N', 'lek dzialajacy na uklad nerwowy'),
    ('A', 'lek dzialajacy na przewod pokarmowy i metabolizm'),
    ('B', 'lek dzialajacy na krew i uklad krwiotworczy'),
    ('C', 'lek dzialajacy na uklad sercowo-naczyniowy'),
    ('G', 'lek dzialajacy na uklad moczowo-plciowy'),
    ('M', 'lek dzialajacy na uklad miesniowo-szkieletowy'),
    ('P', 'lek przeciwpasozytniczy'),
    ('R', 'lek dzialajacy na uklad oddechowy'),
    ('S', 'lek dzialajacy na narzady zmyslow (oczy, uszy)'),
    ('V', 'preparat rozny'),
]


# ===================================================================== pomocnicze
def read_csv(name, encoding):
    with open(DATA / name, encoding=encoding, newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def write_csv(name, header, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(header)
        w.writerows(rows)


def first_line(value):
    return (value or '').split('\n')[0].strip()


def ean13_ok(code):
    d = [int(c) for c in code]
    return (10 - sum(d[i] * (1 if i % 2 == 0 else 3) for i in range(12)) % 10) % 10 == d[12]


def nip_ok(nip):
    if not re.fullmatch(r'\d{10}', nip):
        return False
    w = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    return sum(int(nip[i]) * w[i] for i in range(9)) % 11 == int(nip[9])


def to_ean13(gtin):
    """GTIN-14 z wiodacym zerem == EAN-13. Zwraca None dla kodow niepoprawnych."""
    gtin = (gtin or '').strip()
    if len(gtin) == 14 and gtin[0] == '0':
        gtin = gtin[1:]
    return gtin if len(gtin) == 13 and gtin.isdigit() and ean13_ok(gtin) else None


def ascii_key(text):
    s = unicodedata.normalize('NFKD', text.casefold().replace('ł', 'l'))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', s)).strip()


def normalize_company(name):
    s = ascii_key(name)
    for long, short in (('spolka z ograniczona odpowiedzialnoscia', 'sp z o o'), ('spolka akcyjna', 's a'),
                        ('spolka komandytowa', 'sp k'), ('spolka jawna', 'sp j')):
        s = s.replace(long, short)
    return s.replace(' ', '')   # 'Sp.z o.o.' == 'Sp. z o.o.'


def substance_key(text):
    """'Paracetamolum + Coffeinum' i 'Coffeinum, Paracetamolum' -> ten sam klucz."""
    parts = [p for p in re.split(r'\s*(?:\+|,|;| i | et )\s*', ascii_key(text)) if p]
    return ' + '.join(sorted(set(parts)))


def dose_key(text):
    return re.sub(r'\s+', '', (text or '').casefold().replace(',', '.'))


def parse_date(value):
    value = str(value or '').strip()[:10]
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d-%m-%Y', '%Y.%m.%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def random_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, max((end - start).days, 0)))


def cut(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + '…'


def money(value):
    return float(str(value).replace(' ', '').replace(',', '.'))


COUNT_FORMS = r'(tabl|kaps|sasz|szt|amp|fiol|draż|czop|past|plast|wkł|wstrzyk|ampułko|globul|pastyl|tamp|inhal|dawek)'


def pack_size(text):
    """Wielkosc opakowania jako (rodzaj, ilosc): ('szt', 30) dla tabletek itp., ('obj', 100) dla ml/g."""
    t = (text or '').casefold().replace(',', '.')
    m = re.match(r'\s*(\d+)\s*(?:x|×)\s*(\d+(?:\.\d+)?)\s*(ml|g)\b', t)       # '4 x 200 ml'
    if m:
        return 'obj', float(m.group(1)) * float(m.group(2))
    if re.search(COUNT_FORMS, t):
        m = re.search(r'\d+', t)
        return ('szt', float(m.group())) if m else None
    m = re.search(r'(\d+(?:\.\d+)?)\s*(ml|g)\b', t)
    if m:
        return 'obj', float(m.group(1))
    return None


def opis_atc(atc):
    for prefix, text in OPIS_ATC:
        if atc.startswith(prefix):
            return text
    return 'produkt leczniczy'


# ===================================================================== obwieszczenie MZ
def load_obwieszczenie():
    """Arkusz A1 (leki refundowane w aptece): EAN -> ceny urzedowe."""
    ws = openpyxl.load_workbook(OBWIESZCZENIE, read_only=True)['A1']
    rows = ws.iter_rows(values_only=True)
    next(rows)
    header = list(next(rows))
    idx = {name: header.index(name) for name in header if name}
    ceny = {}
    for r in rows:
        ean = to_ean13(r[idx['Numer GTIN lub inny kod jednoznacznie identyfikujący produkt']])
        if not ean or not r[idx['Cena detaliczna']]:
            continue
        nazwa = str(r[idx['Nazwa  postać i dawka']] or '')
        dawka = nazwa.rsplit(',', 1)[-1] if re.search(r'\d', nazwa.rsplit(',', 1)[-1]) else ''
        ceny[ean] = {
            'detal': money(r[idx['Cena detaliczna']]),
            'hurt': money(r[idx['Cena hurtowa brutto']]),
            'subst': substance_key(str(r[idx['Substancja czynna']] or '')),
            'dawka': dose_key(dawka),
            'size': pack_size(str(r[idx['Zawartość opakowania']] or '')),
        }
    return ceny


class Cennik:
    """Szacowanie cen z ceny jednostkowej (za tabletke / ml) lekow z obwieszczenia."""

    def __init__(self, obw, atc_by_ean):
        self.levels = [defaultdict(list) for _ in range(4)]
        for ean, c in obw.items():
            if not c['size'] or c['size'][1] <= 0:
                continue
            kind, qty = c['size']
            unit = c['detal'] / qty
            atc = atc_by_ean.get(ean, '')
            self.levels[0][(c['subst'], c['dawka'], kind)].append(unit)
            self.levels[1][(c['subst'], kind)].append(unit)
            if len(atc) >= 5:
                self.levels[2][(atc[:5], kind)].append(unit)
            if len(atc) >= 4:
                self.levels[3][(atc[:4], kind)].append(unit)
        ratios = [c['detal'] / c['hurt'] for c in obw.values() if c['hurt'] > 0]
        self.detal_do_hurtu = statistics.median(ratios)

    ZRODLA = ['SZACUNEK_SUBSTANCJA_DAWKA', 'SZACUNEK_SUBSTANCJA', 'SZACUNEK_ATC4', 'SZACUNEK_ATC3']

    def szacuj_cene(self, pack):
        """Kolejno: ta sama substancja i dawka -> ta sama substancja -> grupa ATC 4 poz. -> ATC 3 poz.
        -> model rynkowy (cena za sztuke wg grupy ATC / cena za opakowanie plynu wg kategorii).

        Kazdy szacunek dostaje rozrzut ok. +-15% (rozne marki tej samej substancji)
        i typowa koncowke ceny; losowosc zalezy tylko od EAN, wiec wynik jest powtarzalny.
        """
        rng = random.Random(int(pack['ean']))
        size = pack_size(pack['opak'])
        narzut = NARZUT_OTC if pack['kat'] == 'OTC' else NARZUT_RX_NIEREFUNDOWANY
        price, zrodlo = None, 'SZACUNEK_MODEL_RYNKOWY'
        # Tylko ta sama substancja i tylko opakowania liczone w sztukach. Grupy ATC oraz ml/g
        # dawaly zawyzone ceny (w jednej grupie sa tanie tabletki i drogie ampulki / koncentraty).
        if size and size[0] == 'szt' and size[1] > 0:
            qty = size[1]
            keys = [(pack['subst'], pack['dawka'], 'szt'), (pack['subst'], 'szt')]
            for level, key, name in zip(self.levels, keys, self.ZRODLA):
                if key in level:
                    price, zrodlo = statistics.median(level[key]) * qty * narzut, name
                    break
        if price is None:
            price = model_rynkowy(pack, size)
        # Odchylenie "marki" losowane per produkt (nie per opakowanie), zeby wieksze opakowanie
        # tego samego leku nie wychodzilo tansze od mniejszego.
        marka = random.Random(pack['row']['Identyfikator Produktu Leczniczego'])
        price *= math.exp(marka.gauss(0, 0.15))
        price = min(max(price, CENA_MIN), CENA_MAX_OTC if pack['kat'] == 'OTC' else CENA_MAX_SZACUNEK)
        return round(math.floor(price) + rng.choice(KONCOWKI_CEN), 2), zrodlo


# Model rynkowy dla lekow bez odpowiednika w obwieszczeniu (glownie OTC).
# Typowa cena za sztuke (tabletka, kapsulka, saszetka...) w zl wg grupy ATC - przyblizenie cen
# w polskich aptekach; dopasowanie od najdluzszego prefiksu.
CENA_ZA_SZTUKE = {
    'N02BE': 0.30, 'N02BA': 0.30, 'N02BB': 0.60, 'N02B': 0.45, 'N02C': 2.00, 'N02A': 1.20,
    'M01AE': 0.50, 'M01A': 0.80, 'R05': 0.90, 'R06': 0.60, 'R02': 0.70, 'A11': 0.40, 'A12': 0.45,
    'A02': 0.80, 'A03': 0.70, 'A07': 1.00, 'A10': 0.90, 'B01': 1.20, 'C': 0.50, 'G04': 1.00,
    'N05': 0.80, 'N06': 0.90, 'N03': 1.20, 'J01': 2.50, 'G03': 1.50, 'L': 35.00,
}
CENA_ZA_SZTUKE_KAT = {'OTC': 0.60, 'Rp': 0.90, 'Rpz': 20.00, 'Rpw': 2.00}
STALA_CZESC_CENY = 4.00                                             # marka, opakowanie, ulotka
CENA_100_ML_KAT = {'OTC': 19.0, 'Rp': 28.0, 'Rpz': 250.0, 'Rpw': 45.0}  # syropy, masci, krople...
KONCOWKI_CEN = [0.29, 0.49, 0.69, 0.79, 0.89, 0.99]


def model_rynkowy(pack, size):
    if size and size[0] == 'szt':
        unit = CENA_ZA_SZTUKE_KAT[pack['kat']]
        for prefix in sorted(CENA_ZA_SZTUKE, key=len, reverse=True):
            if pack['atc'].startswith(prefix):
                # leki na recepte zwykle drozsze od odpowiednikow OTC tej samej grupy
                unit = CENA_ZA_SZTUKE[prefix] * (1.3 if pack['kat'] != 'OTC' else 1.0)
                break
        return STALA_CZESC_CENY + size[1] * unit
    base = CENA_100_ML_KAT[pack['kat']]
    if size:   # objetosc: cena rosnie wolniej niz liczba ml
        return base * (max(size[1], 1) / 100) ** 0.35
    return base


# ===================================================================== RPL
def parse_packs(row):
    """Pole 'Opakowanie': linia 'GTIN ¦ kategoria ¦ id', nastepna linia - opis opakowania."""
    out, lines = [], row['Opakowanie'].split('\n')
    for i, line in enumerate(lines):
        parts = [p.strip() for p in line.split('¦')]
        if len(parts) >= 3 and re.fullmatch(r'\d{13,14}', parts[0]):
            desc = lines[i + 1].strip() if i + 1 < len(lines) and '¦' not in lines[i + 1] else ''
            out.append((parts[0], parts[1], desc))
    return out


def producer_of(row):
    """Wytworca leku: wytworca -> wytworca/importer -> importer -> podmiot odpowiedzialny."""
    for name_col, country_col in (('Nazwa wytwórcy', 'Kraj wytwórcy'),
                                  ('Nazwa wytwórcy/importera', 'Kraj wytwórcy/importera'),
                                  ('Nazwa importera', 'Kraj importera')):
        name = first_line(row[name_col])
        if name:
            return name, first_line(row[country_col]) or None
    return row['Podmiot odpowiedzialny'].strip(), None


def load_catalog():
    """Opakowania lekow dla ludzi dostepne w aptece ogolnodostepnej (bez importu rownoleglego)."""
    seen, catalog = set(), []
    for r in read_csv('leki.csv', 'utf-8'):
        if r['Rodzaj preparatu'] != 'Ludzki' or r['Kraj eksportu'].strip():
            continue
        for gtin, kat, desc in parse_packs(r):
            ean = to_ean13(gtin)
            if kat not in KATEGORIE_APTECZNE or not ean or ean in seen:
                continue
            seen.add(ean)
            catalog.append({'row': r, 'ean': ean, 'kat': kat, 'opak': desc,
                            'atc': first_line(r['Kod ATC']),
                            'subst': substance_key(r['Nazwa powszechnie stosowana']),
                            'dawka': dose_key(r['Moc'])})
    return catalog


def select_leki(catalog, n, obw, rng):
    """Asortyment: leki refundowane (prawdziwe ceny) + przeciwbolowe (T1) + reszta, OTC czesciej."""
    catalog = sorted(catalog, key=lambda p: p['ean'])
    is_head = lambda p: p['atc'].startswith(ATC_BOL_GLOWY)
    refund = [p for p in catalog if p['ean'] in obw and not is_head(p)]
    head = [p for p in catalog if is_head(p)]
    chosen = rng.sample(head, min(LIMIT_BOL_GLOWY, len(head), n))
    chosen += rng.sample(refund, min(LIMIT_REFUNDOWANE, len(refund), n - len(chosen)))
    taken = {p['ean'] for p in chosen}
    rest = [p for p in catalog if p['ean'] not in taken]
    # losowanie wazone bez zwracania (Efraimidis-Spirakis)
    weight = {'OTC': 3.0, 'Rp': 1.0, 'Rpz': 0.2, 'Rpw': 0.3}
    rest.sort(key=lambda p: -math.log(rng.random()) / weight[p['kat']])
    return chosen + rest[:max(n - len(chosen), 0)]


def opis_leku(pack):
    r = pack['row']
    head = r['Nazwa Produktu Leczniczego'].strip()
    if r['Nazwa powszechnie stosowana'].strip():
        head += f" ({r['Nazwa powszechnie stosowana'].strip()})"
    parts = [head] + [v for v in (r['Moc'].strip(), first_line(r['Postać farmaceutyczna'])) if v]
    text = ', '.join(parts) + '.'
    if pack['opak']:
        text += f" Opakowanie: {pack['opak']}."
    text += f" {opis_atc(pack['atc']).capitalize()}" + (f" (ATC {pack['atc']})." if pack['atc'] else '.')
    text += f" Kategoria dostepnosci: {pack['kat']} - {OPIS_KATEGORII[pack['kat']]}."
    subst = ' '.join(r['Substancja czynna'].split())
    if subst:
        text += f' Substancja czynna: {subst}.'
    return cut(text, 1000)


def nazwa_leku(pack):
    r = pack['row']
    return cut(', '.join(p for p in (r['Nazwa Produktu Leczniczego'].strip(), r['Moc'].strip(), pack['opak']) if p),
               100)


# ===================================================================== hurtownie
def load_firms():
    """Firmy-wlasciciele hurtowni (bez osob fizycznych), jedna pozycja na NIP."""
    by_nip = {}
    for r in read_csv('hurtownie.csv', 'utf-8-sig'):
        nip = re.sub(r'\D', '', r['właściciel_1_nip'])
        name = ' '.join(r['właściciel_1_nazwa'].split())
        if not name or r['właściciel_1_imię'].strip() or r['właściciel_1_nazwisko'].strip() or not nip_ok(nip):
            continue
        wydane = parse_date(r['zezwolenie_dataWydania'])
        if not wydane:
            continue
        konce = [parse_date(r[c]) for c in ('zezwolenie_dataWygaszeniaZezwolenia', 'zezwolenie_dataCofnięciaZezwolenia')]
        koniec = min([d for d in konce if d], default=None)
        aktywna = r['hurtownia_status'] == 'Aktywna'
        if aktywna:
            koniec = None
        f = by_nip.setdefault(nip, {'nazwa': name, 'nip': nip, 'wydane': wydane, 'koniec': koniec,
                                    'aktywna': aktywna, 'woj': r['hurtownia_adres_województwo'].strip().lower(),
                                    'rodzaje': set()})
        f['rodzaje'].add(r['hurtownia_rodzaj'])
        # firma z kilkoma hurtowniami: najstarsze zezwolenie, aktywna jesli ktorakolwiek aktywna
        f['wydane'] = min(f['wydane'], wydane)
        if aktywna or f['aktywna']:
            f['aktywna'], f['koniec'] = True, None
        elif koniec and (f['koniec'] is None or koniec > f['koniec']):
            f['koniec'] = koniec
    return list(by_nip.values())


def build_dostawcy(firms, rng):
    pool = [f for f in firms if 'Hurtownia' in f['rodzaje']
            and (f['aktywna'] or (f['koniec'] and f['koniec'] >= MIN_KONIEC_ZEZWOLENIA))]
    pool.sort(key=lambda f: f['nip'])
    rng.shuffle(pool)

    rows, meta = [], []
    for f in pool:
        # umowa po uzyskaniu zezwolenia i co najmniej rok przed jego wygasnieciem
        lo = f['wydane'] + timedelta(days=30)
        hi = min(f['koniec'] - timedelta(days=365), date(2026, 9, 30)) if f['koniec'] else date(2026, 9, 30)
        if lo > hi:
            continue
        groups = [g for g in GRUPY_DOSTAWCOW if g[2] <= hi and g[3] >= lo]
        g = rng.choices(groups, weights=[x[1] for x in groups])[0]
        umowa = random_date(rng, max(lo, g[2]), min(hi, g[3]))
        tel = f"+48 {KIERUNKOWE.get(f['woj'], '22')} {rng.randint(200, 899)} {rng.randint(10, 99)} {rng.randint(10, 99)}"
        did = len(rows) + 1
        rows.append([did, cut(f['nazwa'], 100), f['nip'], tel, umowa.isoformat()])
        meta.append([did, f['nip'], 'TAK' if f['aktywna'] else 'NIE', f['wydane'].isoformat(),
                     f['koniec'].isoformat() if f['koniec'] else '', g[0]])
    return rows, meta


# ===================================================================== main
def main():
    rng = random.Random(SEED)

    catalog = load_catalog()
    obw = load_obwieszczenie()
    cennik = Cennik(obw, {p['ean']: p['atc'] for p in catalog})
    leki = select_leki(catalog, LICZBA_LEKOW, obw, rng)
    leki.sort(key=lambda p: (normalize_company(producer_of(p['row'])[0]), p['ean']))

    firms = load_firms()
    nip_by_name = {normalize_company(f['nazwa']): f['nip'] for f in firms}

    # ---------------- Producent + Lek
    producenci, lek_rows, ceny_rows, used_nip = {}, [], [], set()
    for p in leki:
        name, kraj = producer_of(p['row'])
        key = normalize_company(name)
        if key not in producenci:
            nip = nip_by_name.get(key)
            nip = nip if nip and nip not in used_nip else None
            if nip:
                used_nip.add(nip)
            producenci[key] = {'id': len(producenci) + 1, 'nazwa': cut(name, 100), 'nip': nip,
                               'kraj': cut(kraj, 50) if kraj else None, 'min_wprow': None}
        prod = producenci[key]

        if p['ean'] in obw:
            detal, hurt, zrodlo = obw[p['ean']]['detal'], obw[p['ean']]['hurt'], 'OBWIESZCZENIE_MZ_2026-10'
        else:
            detal, zrodlo = cennik.szacuj_cene(p)
            hurt = round(detal / cennik.detal_do_hurtu, 2)

        # 85% lekow w systemie przed poczatkiem historii sprzedazy, 15% wprowadzane pozniej
        if rng.random() < 0.85:
            wprow = random_date(rng, date(2015, 1, 1), POCZATEK_HISTORII - timedelta(days=1))
        else:
            wprow = random_date(rng, POCZATEK_HISTORII, date(2026, 4, 30))
        prod['min_wprow'] = min(prod['min_wprow'] or wprow, wprow)

        lid = len(lek_rows) + 1
        lek_rows.append([lid, nazwa_leku(p), p['ean'], f'{detal:.2f}', wprow.isoformat(), prod['id'], opis_leku(p)])
        ceny_rows.append([lid, p['ean'], p['kat'], f'{hurt:.2f}', f'{detal:.2f}', zrodlo])

    prod_rows = []
    for prod in sorted(producenci.values(), key=lambda x: x['id']):
        wsp = max(date(2010, 1, 1), prod['min_wprow'] - timedelta(days=rng.randint(30, 3 * 365)))
        prod_rows.append([prod['id'], prod['nazwa'], prod['nip'] or '', prod['kraj'] or '', wsp.isoformat()])

    dost_rows, dost_meta = build_dostawcy(firms, rng)

    write_csv('producent.csv', ['ID', 'Nazwa', 'NIP', 'Kraj', 'DataRozpoczeciaWspolpracy'], prod_rows)
    write_csv('lek.csv', ['ID', 'Nazwa', 'KodEAN', 'CenaDetaliczna', 'DataWprowadzenia', 'ProducentID',
                          'OpisLeku'], lek_rows)
    write_csv('dostawca.csv', ['ID', 'Nazwa', 'NIP', 'Telefon', 'DataPodpisaniaUmowy'], dost_rows)
    write_csv('lek_ceny.csv', ['LekID', 'KodEAN', 'Kategoria', 'CenaHurtowaBrutto', 'CenaDetaliczna',
                               'ZrodloCeny'], ceny_rows)
    write_csv('dostawca_meta.csv', ['DostawcaID', 'NIP', 'HurtowniaAktywna', 'DataZezwolenia',
                                    'DataKoncaZezwolenia', 'GrupaStazu'], dost_meta)

    # ---------------- podsumowanie
    zrodla = Counter(r[5] for r in ceny_rows)
    print(f'Katalog RPL (ludzkie, apteczne, bez importu rownoleglego): {len(catalog)} opakowan')
    print(f'Obwieszczenie MZ (A1): {len(obw)} EAN, mediana cena detaliczna/hurtowa = {cennik.detal_do_hurtu:.3f}')
    print(f'Lek:       {len(lek_rows)}  kategorie={dict(Counter(p["kat"] for p in leki))}  '
          f'przeciwbolowe/migrena={sum(p["atc"].startswith(ATC_BOL_GLOWY) for p in leki)}')
    print(f'  zrodla cen: {dict(zrodla)}')
    print(f'Producent: {len(prod_rows)}  z NIP={sum(1 for r in prod_rows if r[2])}  '
          f'kraje={len({r[3] for r in prod_rows})}')
    print(f'Dostawca:  {len(dost_rows)}  staz={dict(Counter(m[5] for m in dost_meta))}  '
          f'aktywne={sum(m[2] == "TAK" for m in dost_meta)}')
    print(f'Zapisano do: {OUT.relative_to(ROOT)}/')


if __name__ == '__main__':
    main()
