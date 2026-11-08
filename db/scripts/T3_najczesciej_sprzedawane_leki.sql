-- T3 - Najczesciej sprzedawane leki i ich producenci
-- Przychod uwzglednia rabat z pozycji sprzedazy.
-- Srednia liczba opakowan jest liczona dla wszystkich lekow, takze bez sprzedazy.

SprzedazLekow AS (
    SELECT
        l.ID AS LekID,
        l.Nazwa AS Lek,
        p.ID AS ProducentID,
        p.Nazwa AS Producent,
        COALESCE(SUM(ps.Ilosc), 0) AS LiczbaSprzedanychOpakowan,
        COALESCE(
            SUM(ps.Ilosc * ps.CenaSprzedazy * (1 - ps.Rabat / 100)),
            0
        ) AS Przychod
    FROM Lek l
    JOIN Producent p
        ON p.ID = l.ProducentID
    LEFT JOIN PozycjaSprzedazy ps
        ON ps.LekID = l.ID
    LEFT JOIN Sprzedaz s
        ON s.ID = ps.SprzedazID
    GROUP BY l.ID, l.Nazwa, p.ID, p.Nazwa
),
SprzedazZeSrednia AS (
    SELECT
        sl.*,
        AVG(sl.LiczbaSprzedanychOpakowan) OVER () AS SredniaSprzedazNaLek
    FROM SprzedazLekow sl
)
SELECT
    LekID,
    Lek,
    ProducentID,
    Producent,
    LiczbaSprzedanychOpakowan,
    Przychod,
    SredniaSprzedazNaLek
FROM SprzedazZeSrednia
WHERE LiczbaSprzedanychOpakowan > SredniaSprzedazNaLek
ORDER BY LiczbaSprzedanychOpakowan DESC, Lek;
