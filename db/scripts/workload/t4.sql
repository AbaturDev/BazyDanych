SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

-- T4.1 Nagłówki zamówień
INSERT INTO Zamowienie (DostawcaID, DataZamowienia, PlanowanaDostawa, Status,
                        WartoscZamowienia, KodZamowienia)
WITH sprzedaz_12m AS (
    SELECT ps.LekID,
           SUM(ps.Ilosc) AS Sprzedano12m,
           SUM(CASE WHEN s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -3)
                    THEN ps.Ilosc ELSE 0 END) AS Sprzedano3m
    FROM   PozycjaSprzedazy ps
    JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
    WHERE  s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -12)
    GROUP  BY ps.LekID
    HAVING SUM(ps.Ilosc) >= 100
    AND    SUM(CASE WHEN s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -3)
                    THEN ps.Ilosc ELSE 0 END) / 3 >= 0.7 * SUM(ps.Ilosc) / 12
),
wiarygodni_dostawcy AS (
    SELECT z.DostawcaID
    FROM   Zamowienie z
    LEFT   JOIN PozycjaZamowienia pz ON pz.ZamowienieID = z.ID
    GROUP  BY z.DostawcaID
    HAVING COUNT(DISTINCT CASE WHEN z.Status = 'ANULOWANE' THEN z.ID END)
           < 0.05 * COUNT(DISTINCT z.ID)
    AND    AVG(pz.DataDostarczenia - z.PlanowanaDostawa) <= 1
),
ostatnia_dostawa AS (
    SELECT pz.LekID,
           z.DostawcaID,
           pz.CenaZakupu,
           ROW_NUMBER() OVER (PARTITION BY pz.LekID
                              ORDER BY pz.DataDostarczenia DESC, pz.ID DESC) AS rn
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    JOIN   Dostawca   d ON d.ID = z.DostawcaID
    JOIN   wiarygodni_dostawcy wd ON wd.DostawcaID = z.DostawcaID
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    AND    d.DataPodpisaniaUmowy <= ADD_MONTHS(SYSDATE, -36)
),
dostarczone AS (
    SELECT pz.LekID, SUM(pz.Ilosc) AS Dostarczono
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    GROUP  BY pz.LekID
),
sprzedane AS (
    SELECT ps.LekID, SUM(ps.Ilosc) AS Sprzedano
    FROM   PozycjaSprzedazy ps
    GROUP  BY ps.LekID
),
kandydaci AS (
    SELECT s.LekID, od.DostawcaID, od.CenaZakupu,
           2 * GREATEST(s.Sprzedano12m / 12, s.Sprzedano3m / 3)      AS Zapotrzebowanie,
           GREATEST(NVL(dz.Dostarczono, 0) - NVL(sz.Sprzedano, 0), 0) AS Zapas
    FROM   sprzedaz_12m s
    JOIN   ostatnia_dostawa od ON od.LekID = s.LekID AND od.rn = 1
    LEFT   JOIN dostarczone dz ON dz.LekID = s.LekID
    LEFT   JOIN sprzedane   sz ON sz.LekID = s.LekID
    WHERE  NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz
               JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
               WHERE  pz.LekID = s.LekID
               AND    z.Status IN ('NOWE', 'ZATWIERDZONE', 'W_REALIZACJI'))
    AND    GREATEST(NVL(dz.Dostarczono, 0) - NVL(sz.Sprzedano, 0), 0)
           < 2 * GREATEST(s.Sprzedano12m / 12, s.Sprzedano3m / 3)
)
SELECT k.DostawcaID,
       TRUNC(SYSDATE),
       TRUNC(SYSDATE) + 3,
       'NOWE',
       0,
       'Z' || LPAD(m.MaxNr + ROW_NUMBER() OVER (ORDER BY k.DostawcaID), 9, '0')
FROM   (SELECT DISTINCT DostawcaID FROM kandydaci) k
CROSS  JOIN (SELECT NVL(MAX(TO_NUMBER(SUBSTR(KodZamowienia, 2))), 0) AS MaxNr
             FROM   Zamowienie) m;

-- T4.2 Pozycje zamówień
INSERT INTO PozycjaZamowienia (ZamowienieID, LekID, Ilosc, CenaZakupu,
                               DataDostarczenia, KodPozycji)
WITH sprzedaz_12m AS (
    SELECT ps.LekID,
           SUM(ps.Ilosc) AS Sprzedano12m,
           SUM(CASE WHEN s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -3)
                    THEN ps.Ilosc ELSE 0 END) AS Sprzedano3m
    FROM   PozycjaSprzedazy ps
    JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
    WHERE  s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -12)
    GROUP  BY ps.LekID
    HAVING SUM(ps.Ilosc) >= 100
    AND    SUM(CASE WHEN s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -3)
                    THEN ps.Ilosc ELSE 0 END) / 3 >= 0.7 * SUM(ps.Ilosc) / 12
),
wiarygodni_dostawcy AS (
    SELECT z.DostawcaID
    FROM   Zamowienie z
    LEFT   JOIN PozycjaZamowienia pz ON pz.ZamowienieID = z.ID
    GROUP  BY z.DostawcaID
    HAVING COUNT(DISTINCT CASE WHEN z.Status = 'ANULOWANE' THEN z.ID END)
           < 0.05 * COUNT(DISTINCT z.ID)
    AND    AVG(pz.DataDostarczenia - z.PlanowanaDostawa) <= 1
),
ostatnia_dostawa AS (
    SELECT pz.LekID,
           z.DostawcaID,
           pz.CenaZakupu,
           ROW_NUMBER() OVER (PARTITION BY pz.LekID
                              ORDER BY pz.DataDostarczenia DESC, pz.ID DESC) AS rn
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    JOIN   Dostawca   d ON d.ID = z.DostawcaID
    JOIN   wiarygodni_dostawcy wd ON wd.DostawcaID = z.DostawcaID
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    AND    d.DataPodpisaniaUmowy <= ADD_MONTHS(SYSDATE, -36)
),
dostarczone AS (
    SELECT pz.LekID, SUM(pz.Ilosc) AS Dostarczono
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    GROUP  BY pz.LekID
),
sprzedane AS (
    SELECT ps.LekID, SUM(ps.Ilosc) AS Sprzedano
    FROM   PozycjaSprzedazy ps
    GROUP  BY ps.LekID
),
kandydaci AS (
    SELECT s.LekID, od.DostawcaID, od.CenaZakupu,
           2 * GREATEST(s.Sprzedano12m / 12, s.Sprzedano3m / 3)      AS Zapotrzebowanie,
           GREATEST(NVL(dz.Dostarczono, 0) - NVL(sz.Sprzedano, 0), 0) AS Zapas
    FROM   sprzedaz_12m s
    JOIN   ostatnia_dostawa od ON od.LekID = s.LekID AND od.rn = 1
    LEFT   JOIN dostarczone dz ON dz.LekID = s.LekID
    LEFT   JOIN sprzedane   sz ON sz.LekID = s.LekID
    WHERE  NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz
               JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
               WHERE  pz.LekID = s.LekID
               AND    z.Status IN ('NOWE', 'ZATWIERDZONE', 'W_REALIZACJI'))
    AND    GREATEST(NVL(dz.Dostarczono, 0) - NVL(sz.Sprzedano, 0), 0)
           < 2 * GREATEST(s.Sprzedano12m / 12, s.Sprzedano3m / 3)
),
nowe_zamowienia AS (
    SELECT z.ID, z.DostawcaID
    FROM   Zamowienie z
    WHERE  z.Status            = 'NOWE'
    AND    z.DataZamowienia    = TRUNC(SYSDATE)
    AND    z.WartoscZamowienia = 0
    AND    NOT EXISTS (SELECT 1 FROM PozycjaZamowienia pz WHERE pz.ZamowienieID = z.ID)
)
SELECT nz.ID,
       k.LekID,
       CEIL(k.Zapotrzebowanie - k.Zapas),
       GREATEST(ROUND(k.CenaZakupu * (1 + DBMS_RANDOM.VALUE(-0.05, 0.05)), 2), 0.01),
       NULL,
       'ZP' || LPAD(m.MaxNr + ROW_NUMBER() OVER (ORDER BY nz.ID, k.LekID), 6, '0')
FROM   kandydaci k
JOIN   nowe_zamowienia nz ON nz.DostawcaID = k.DostawcaID
CROSS  JOIN (SELECT NVL(MAX(TO_NUMBER(SUBSTR(KodPozycji, 3))), 0) AS MaxNr
             FROM   PozycjaZamowienia) m;

-- T4.3 Wartość nowych zamówień
UPDATE Zamowienie z
SET    z.WartoscZamowienia = (SELECT SUM(pz.Ilosc * pz.CenaZakupu)
                              FROM   PozycjaZamowienia pz
                              WHERE  pz.ZamowienieID = z.ID)
WHERE  z.Status            = 'NOWE'
AND    z.DataZamowienia    = TRUNC(SYSDATE)
AND    z.WartoscZamowienia = 0
AND    EXISTS (SELECT 1 FROM PozycjaZamowienia pz WHERE pz.ZamowienieID = z.ID);

ROLLBACK;
