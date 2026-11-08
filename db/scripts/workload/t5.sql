SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

UPDATE Lek l
SET    l.CenaDetaliczna = ROUND(l.CenaDetaliczna * w.WzrostKosztu, 2)
FROM  (
    SELECT c.LekID,
           c.SredniaCena6m / c.SredniaCenaPoprz24m AS WzrostKosztu
    FROM  (
        SELECT pz.LekID,
               AVG(CASE WHEN z.DataZamowienia >= ADD_MONTHS(SYSDATE, -6)
                        THEN pz.CenaZakupu END) AS SredniaCena6m,
               AVG(CASE WHEN z.DataZamowienia <  ADD_MONTHS(SYSDATE, -6)
                        THEN pz.CenaZakupu END) AS SredniaCenaPoprz24m
        FROM   PozycjaZamowienia pz
        JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
        WHERE  z.Status = 'ZREALIZOWANE'
        AND    z.DataZamowienia >= ADD_MONTHS(SYSDATE, -30)
        GROUP  BY pz.LekID
    ) c
    JOIN  (
        SELECT ps.LekID
        FROM   PozycjaSprzedazy ps
        JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
        WHERE  s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -12)
        GROUP  BY ps.LekID
        HAVING SUM(ps.Ilosc) > 20
    ) sp ON sp.LekID = c.LekID
    WHERE  c.SredniaCena6m >= 1.05 * c.SredniaCenaPoprz24m
) w
WHERE  l.ID = w.LekID;

ROLLBACK;
