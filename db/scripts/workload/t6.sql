SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

DELETE FROM PozycjaSprzedazy
WHERE LekID IN (
    SELECT l.ID
    FROM Lek l
    WHERE NOT EXISTS (
        SELECT 1
        FROM PozycjaSprzedazy ps_nowsza
        JOIN Sprzedaz s ON s.ID = ps_nowsza.SprzedazID
        WHERE ps_nowsza.LekID = l.ID
          AND s.DataSprzedazy >= ADD_MONTHS(TRUNC(SYSDATE), -36)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM PozycjaZamowienia pz
        JOIN Zamowienie z ON z.ID = pz.ZamowienieID
        WHERE pz.LekID = l.ID
          AND z.Status IN ('NOWE', 'ZATWIERDZONE', 'W_REALIZACJI')
    )
);

ROLLBACK;
