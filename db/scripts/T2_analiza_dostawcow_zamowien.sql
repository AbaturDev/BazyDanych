-- T2 - Analiza dostawcow i zamowien
-- Operacja typu SELECT: przychod producentow po rabatach,
-- szacowana marza, liczba sprzedanych opakowan i liczba lekow w ofercie.
-- Srednia cena zakupu leku jest wazona ilosciami z zamowien zrealizowanych.

WITH SprzedazLek AS (
    SELECT
        ps.LekID,
        SUM(ps.Ilosc) AS LiczbaOpakowan,
        SUM(ps.Ilosc * ps.CenaSprzedazy * (1 - ps.Rabat / 100)) AS Przychod
    FROM PozycjaSprzedazy ps
    JOIN Sprzedaz s
        ON s.ID = ps.SprzedazID
    GROUP BY ps.LekID
),
SredniaCenaZakupu AS (
    SELECT
        pz.LekID,
        SUM(pz.Ilosc * pz.CenaZakupu) / NULLIF(SUM(pz.Ilosc), 0) AS CenaZakupu
    FROM PozycjaZamowienia pz
    JOIN Zamowienie z
        ON z.ID = pz.ZamowienieID
    WHERE z.Status = 'ZREALIZOWANE'
    GROUP BY pz.LekID
),
WynikiProducentow AS (
    SELECT
        p.ID AS ProducentID,
        p.Nazwa AS Producent,
        COALESCE(SUM(sl.Przychod), 0) AS Przychod,
        COALESCE(
            SUM(sl.Przychod - sl.LiczbaOpakowan * COALESCE(szk.CenaZakupu, 0)),
            0
        ) AS SzacowanaMarza,
        COALESCE(SUM(sl.LiczbaOpakowan), 0) AS LiczbaSprzedanychOpakowan,
        COUNT(DISTINCT l.ID) AS LiczbaRoznychLekow
    FROM Producent p
    LEFT JOIN Lek l
        ON l.ProducentID = p.ID
    LEFT JOIN SprzedazLek sl
        ON sl.LekID = l.ID
    LEFT JOIN SredniaCenaZakupu szk
        ON szk.LekID = l.ID
    GROUP BY p.ID, p.Nazwa
),
WynikiZeSrednia AS (
    SELECT
        wp.*,
        AVG(wp.Przychod) OVER () AS SredniPrzychodProducenta
    FROM WynikiProducentow wp
)
SELECT
    ProducentID,
    Producent,
    Przychod,
    SzacowanaMarza,
    LiczbaSprzedanychOpakowan,
    LiczbaRoznychLekow,
    SredniPrzychodProducenta
FROM WynikiZeSrednia
WHERE Przychod > SredniPrzychodProducenta
ORDER BY Przychod DESC;
