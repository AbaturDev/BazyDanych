SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

-- T4.1 Nagłówki zamówień
INSERT INTO Zamowienie (DostawcaID, DataZamowienia, PlanowanaDostawa, Status,
                        WartoscZamowienia, KodZamowienia)
WITH sprzedaz_12m AS (
    SELECT ps.LekID,
           SUM(ps.Ilosc) AS Sprzedano12m
    FROM   PozycjaSprzedazy ps
    JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
    WHERE  s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -12)
    GROUP  BY ps.LekID
    HAVING SUM(ps.Ilosc) >= 300
),
ostatnia_dostawa AS (
    SELECT pz.LekID,
           z.DostawcaID,
           ROW_NUMBER() OVER (PARTITION BY pz.LekID
                              ORDER BY pz.DataDostarczenia DESC, pz.ID DESC) AS rn
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    JOIN   Dostawca   d ON d.ID = z.DostawcaID
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    AND    d.DataPodpisaniaUmowy <= ADD_MONTHS(SYSDATE, -36)
),
kandydaci AS (
    SELECT s.LekID, od.DostawcaID
    FROM   sprzedaz_12m s
    JOIN   ostatnia_dostawa od ON od.LekID = s.LekID AND od.rn = 1
    WHERE  NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz
               JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
               WHERE  pz.LekID = s.LekID
               AND    z.Status IN ('NOWE', 'ZATWIERDZONE', 'W_REALIZACJI'))
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
    HAVING SUM(ps.Ilosc) >= 300
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
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    AND    d.DataPodpisaniaUmowy <= ADD_MONTHS(SYSDATE, -36)
),
kandydaci AS (
    SELECT s.LekID, od.DostawcaID, od.CenaZakupu, s.Sprzedano12m, s.Sprzedano3m
    FROM   sprzedaz_12m s
    JOIN   ostatnia_dostawa od ON od.LekID = s.LekID AND od.rn = 1
    WHERE  NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz
               JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
               WHERE  pz.LekID = s.LekID
               AND    z.Status IN ('NOWE', 'ZATWIERDZONE', 'W_REALIZACJI'))
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
       CEIL(2 * GREATEST(k.Sprzedano12m / 12, k.Sprzedano3m / 3)),
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
