SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

UPDATE Lek l
SET    l.CenaDetaliczna = ROUND(l.CenaDetaliczna * LEAST(w.WzrostKosztu, 1.20), 2)
FROM  (
    SELECT c.LekID,
           c.Koszt6m,
           c.Koszt6m / c.KosztPoprz24m AS WzrostKosztu
    FROM  (
        SELECT pz.LekID,
               SUM(CASE WHEN z.DataZamowienia >= ADD_MONTHS(SYSDATE, -6)
                        THEN pz.Ilosc * pz.CenaZakupu END)
             / SUM(CASE WHEN z.DataZamowienia >= ADD_MONTHS(SYSDATE, -6)
                        THEN pz.Ilosc END)                           AS Koszt6m,
               SUM(CASE WHEN z.DataZamowienia <  ADD_MONTHS(SYSDATE, -6)
                        THEN pz.Ilosc * pz.CenaZakupu END)
             / SUM(CASE WHEN z.DataZamowienia <  ADD_MONTHS(SYSDATE, -6)
                        THEN pz.Ilosc END)                           AS KosztPoprz24m
        FROM   PozycjaZamowienia pz
        JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
        JOIN   Dostawca   d ON d.ID = z.DostawcaID
        WHERE  z.Status = 'ZREALIZOWANE'
        AND    z.DataZamowienia      >= ADD_MONTHS(SYSDATE, -30)
        AND    d.DataPodpisaniaUmowy <= ADD_MONTHS(SYSDATE, -12)
        GROUP  BY pz.LekID
        HAVING COUNT(CASE WHEN z.DataZamowienia >= ADD_MONTHS(SYSDATE, -6)
                          THEN 1 END) >= 2
        AND    COUNT(DISTINCT CASE WHEN z.DataZamowienia >= ADD_MONTHS(SYSDATE, -6)
                                   THEN z.DostawcaID END) >= 2
    ) c
    JOIN  (
        SELECT ps.LekID
        FROM   PozycjaSprzedazy ps
        JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
        WHERE  s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -12)
        GROUP  BY ps.LekID
        HAVING SUM(ps.Ilosc) > 5
        AND    SUM(CASE WHEN s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -6)
                        THEN ps.Ilosc ELSE 0 END)
               >= 0.5 * SUM(CASE WHEN s.DataSprzedazy < ADD_MONTHS(SYSDATE, -6)
                                 THEN ps.Ilosc ELSE 0 END)
    ) sp ON sp.LekID = c.LekID
    WHERE  c.Koszt6m >= 1.03 * c.KosztPoprz24m
    AND    NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz2
               JOIN   Zamowienie z2 ON z2.ID = pz2.ZamowienieID
               WHERE  pz2.LekID = c.LekID
               AND    z2.Status IN ('ZATWIERDZONE', 'W_REALIZACJI'))
) w
WHERE  l.ID = w.LekID
AND    (l.CenaDetaliczna - w.Koszt6m) / l.CenaDetaliczna < 0.35;

ROLLBACK;
