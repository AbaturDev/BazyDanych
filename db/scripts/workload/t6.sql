SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

DELETE FROM PozycjaSprzedazy ps
WHERE  ps.SprzedazID IN (
           SELECT s.ID
           FROM   Sprzedaz s
           WHERE  s.DataSprzedazy < ADD_MONTHS(TRUNC(SYSDATE), -36)
       )
AND    ps.LekID IN (
    SELECT l.ID
    FROM   Lek l
    WHERE  -- 1. brak sprzedazy w ostatnich 36 miesiacach
           NOT EXISTS (
               SELECT 1
               FROM   PozycjaSprzedazy p2
               JOIN   Sprzedaz s2 ON s2.ID = p2.SprzedazID
               WHERE  p2.LekID = l.ID
               AND    s2.DataSprzedazy >= ADD_MONTHS(TRUNC(SYSDATE), -36))
    -- 2. brak aktywnych zamowien
    AND    NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz
               JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
               WHERE  pz.LekID = l.ID
               AND    z.Status IN ('NOWE', 'ZATWIERDZONE', 'W_REALIZACJI'))
    -- 3. brak jakichkolwiek dostaw w ostatnich 24 miesiacach
    AND    NOT EXISTS (
               SELECT 1
               FROM   PozycjaZamowienia pz
               JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
               WHERE  pz.LekID = l.ID
               AND    pz.DataDostarczenia >= ADD_MONTHS(TRUNC(SYSDATE), -24))
    -- 4. lacznie sprzedano malo opakowan w calej historii
    AND    (SELECT NVL(SUM(p3.Ilosc), 0)
            FROM   PozycjaSprzedazy p3
            WHERE  p3.LekID = l.ID) < 
           (SELECT 0.5 * AVG(sumy.Suma)
            FROM  (SELECT SUM(p4.Ilosc) AS Suma
                   FROM   PozycjaSprzedazy p4
                   GROUP  BY p4.LekID) sumy)
    -- 5. sprzedaz leku ponizej sredniej jego producenta
    AND    (SELECT NVL(SUM(p5.Ilosc), 0)
            FROM   PozycjaSprzedazy p5
            WHERE  p5.LekID = l.ID) <
           (SELECT AVG(sp.Suma)
            FROM  (SELECT l2.ProducentID, l2.ID AS LekID, SUM(p6.Ilosc) AS Suma
                   FROM   Lek l2
                   JOIN   PozycjaSprzedazy p6 ON p6.LekID = l2.ID
                   GROUP  BY l2.ProducentID, l2.ID) sp
            WHERE  sp.ProducentID = l.ProducentID)
    -- 6. cena detaliczna ponizej sredniej producenta
    AND    l.CenaDetaliczna < (SELECT AVG(l3.CenaDetaliczna)
                               FROM   Lek l3
                               WHERE  l3.ProducentID = l.ProducentID)
);

ROLLBACK;