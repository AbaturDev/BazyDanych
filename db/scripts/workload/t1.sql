SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

WITH sprzedaz_lekow AS (
    SELECT l.ID                                                      AS LekID,
           l.Nazwa                                                   AS Lek,
           pr.Nazwa                                                  AS Producent,
           SUM(ps.Ilosc)                                             AS SprzedaneOpakowania,
           COUNT(DISTINCT s.ID)                                      AS LiczbaTransakcji,
           ROUND(SUM(ps.Ilosc * ps.CenaSprzedazy * (1 - ps.Rabat / 100)), 2)
                                                                     AS Przychod,
           ROUND(SUM(ps.Ilosc * (ps.CenaSprzedazy * (1 - ps.Rabat / 100)
                                 - dost.CenaZakupu)), 2)             AS Marza
    FROM   Lek l
    JOIN   Producent        pr ON pr.ID = l.ProducentID
    JOIN   PozycjaSprzedazy ps ON ps.LekID = l.ID
    JOIN   Sprzedaz         s  ON s.ID  = ps.SprzedazID
    CROSS  APPLY (
        SELECT pz.CenaZakupu
        FROM   PozycjaZamowienia pz
        JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
        JOIN   Dostawca   d ON d.ID = z.DostawcaID
        WHERE  pz.LekID               = ps.LekID
        AND    pz.DataDostarczenia   <= s.DataSprzedazy
        AND    pz.CenaZakupu          < l.CenaDetaliczna
        AND    z.Status               = 'ZREALIZOWANE'
        AND    z.DataZamowienia      >= ADD_MONTHS(SYSDATE, -36)
        AND    d.DataPodpisaniaUmowy <= ADD_MONTHS(SYSDATE, -60)
        ORDER  BY pz.DataDostarczenia DESC, pz.ID DESC
        FETCH  FIRST 1 ROW ONLY
    ) dost
    WHERE  s.DataSprzedazy >= ADD_MONTHS(SYSDATE, -12)
    AND    (l.OpisLeku LIKE N'%migren%' OR l.OpisLeku LIKE N'%bólu głowy%')
    GROUP  BY l.ID, l.Nazwa, pr.Nazwa
)
SELECT Lek,
       Producent,
       SprzedaneOpakowania,
       LiczbaTransakcji,
       Przychod,
       Marza
FROM   sprzedaz_lekow
WHERE  SprzedaneOpakowania >= 100
AND    Przychod > (SELECT AVG(Przychod) FROM sprzedaz_lekow)
ORDER  BY Przychod DESC;
