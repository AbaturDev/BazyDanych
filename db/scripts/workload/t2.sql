SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

WITH sprzedaz_lek_msc AS (
    SELECT ps.LekID,
           TRUNC(s.DataSprzedazy, 'MM')                                AS Miesiac,
           SUM(ps.Ilosc)                                               AS Opakowania,
           COUNT(DISTINCT s.ID)                                        AS Transakcje,
           SUM(ps.Ilosc * ps.CenaSprzedazy * (1 - ps.Rabat / 100))     AS Przychod,
           SUM(ps.Ilosc * ps.CenaSprzedazy * ps.Rabat / 100)           AS WartoscRabatow,
           AVG(ps.CenaSprzedazy)                                       AS SredniaCena,
           STDDEV(ps.CenaSprzedazy)                                    AS OdchCena
    FROM   PozycjaSprzedazy ps
    JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
    GROUP  BY ps.LekID, TRUNC(s.DataSprzedazy, 'MM')
),
koszt_lek_msc AS (
    SELECT pz.LekID,
           TRUNC(z.DataZamowienia, 'MM')                               AS Miesiac,
           SUM(pz.Ilosc * pz.CenaZakupu) / NULLIF(SUM(pz.Ilosc), 0)    AS SredniaCenaZakupu,
           SUM(pz.Ilosc)                                               AS Zamowione,
           COUNT(DISTINCT z.DostawcaID)                                AS LiczbaDostawcow,
           AVG(pz.DataDostarczenia - z.PlanowanaDostawa)               AS SrednieOpoznienieDni
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    WHERE  z.Status = 'ZREALIZOWANE'
    AND    pz.DataDostarczenia IS NOT NULL
    GROUP  BY pz.LekID, TRUNC(z.DataZamowienia, 'MM')
),
lek_msc AS (
    SELECT l.ProducentID, l.ID AS LekID, sl.Miesiac,
           sl.Opakowania, sl.Transakcje, sl.Przychod, sl.WartoscRabatow,
           sl.OdchCena / NULLIF(sl.SredniaCena, 0)                     AS ZmiennoscCeny,
           sl.Przychod - sl.Opakowania *
               NVL(k.SredniaCenaZakupu,
                   AVG(k.SredniaCenaZakupu) OVER (PARTITION BY l.ID))  AS Marza,
           NVL(k.Zamowione, 0)                                         AS Zamowione,
           NVL(k.LiczbaDostawcow, 0)                                   AS LiczbaDostawcow,
           k.SrednieOpoznienieDni
    FROM   Lek l
    JOIN   sprzedaz_lek_msc sl ON sl.LekID = l.ID
    LEFT   JOIN koszt_lek_msc k ON k.LekID = l.ID AND k.Miesiac = sl.Miesiac
),
producent_msc AS (
    SELECT ProducentID, Miesiac,
           SUM(Przychod)               AS Przychod,
           SUM(Marza)                  AS Marza,
           SUM(Opakowania)             AS Opakowania,
           SUM(Transakcje)             AS Transakcje,
           SUM(WartoscRabatow)         AS WartoscRabatow,
           SUM(Zamowione)              AS Zamowione,
           COUNT(DISTINCT LekID)       AS LiczbaLekow,
           MAX(LiczbaDostawcow)        AS MaxDostawcow,
           AVG(SrednieOpoznienieDni)   AS SrOpoznienie,
           AVG(ZmiennoscCeny)          AS SrZmiennoscCeny
    FROM   lek_msc
    GROUP  BY ProducentID, Miesiac
),
producent_okno AS (
    SELECT pm.*,
           MONTHS_BETWEEN(Miesiac, DATE '2000-01-01')                  AS NrMsc,
           SUM(Przychod) OVER (PARTITION BY ProducentID ORDER BY Miesiac
                               ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS Przychod12m,
           AVG(Przychod) OVER (PARTITION BY ProducentID ORDER BY Miesiac
                               ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)  AS SredniaRuchoma3m,
           LAG(Przychod, 12) OVER (PARTITION BY ProducentID ORDER BY Miesiac) AS PrzychodRokTemu,
           RATIO_TO_REPORT(Przychod) OVER (PARTITION BY Miesiac)       AS UdzialMsc,
           RANK() OVER (PARTITION BY Miesiac ORDER BY Przychod DESC)   AS RankMsc
    FROM   producent_msc pm
),
producent_podsumowanie AS (
    SELECT ProducentID,
           COUNT(*)                                                    AS Miesiace,
           SUM(Przychod)                                               AS Przychod,
           SUM(Marza)                                                  AS Marza,
           SUM(Opakowania)                                             AS Opakowania,
           SUM(Transakcje)                                             AS Transakcje,
           SUM(WartoscRabatow)                                         AS WartoscRabatow,
           MAX(LiczbaLekow)                                            AS LiczbaLekow,
           MAX(MaxDostawcow)                                           AS MaxDostawcow,
           AVG(SrOpoznienie)                                           AS SrOpoznienie,
           AVG(SrZmiennoscCeny)                                        AS SrZmiennoscCeny,
           AVG(UdzialMsc)                                              AS SredniUdzial,
           MIN(RankMsc)                                                AS NajlepszaPozycja,
           SUM(CASE WHEN Przychod > PrzychodRokTemu THEN 1 ELSE 0 END) AS MiesiaceWzrostu,
           COUNT(PrzychodRokTemu)                                      AS MiesiaceZPorownaniem,
           MAX(Przychod12m)                                            AS MaxPrzychod12m,
           REGR_SLOPE(Przychod, NrMsc)                                 AS NachylenieTrendu,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY Przychod)       AS MedianaMiesieczna
    FROM   producent_okno
    GROUP  BY ProducentID
),
wyniki AS (
    SELECT pp.*,
           AVG(Przychod)  OVER ()                                      AS SredniPrzychod,
           PERCENT_RANK() OVER (ORDER BY Marza / NULLIF(Przychod, 0))  AS PercentylMarzy,
           RANK()         OVER (ORDER BY Przychod DESC)                AS RankOgolny
    FROM   producent_podsumowanie pp
)
SELECT p.ID AS ProducentID, p.Nazwa AS Producent,
       ROUND(w.Przychod, 2)                                            AS Przychod,
       ROUND(w.Marza, 2)                                               AS Marza,
       ROUND(100 * w.Marza / NULLIF(w.Przychod, 0), 2)                 AS MarzaProc,
       ROUND(100 * w.WartoscRabatow / NULLIF(w.Przychod + w.WartoscRabatow, 0), 2) AS RabatProc,
       w.Opakowania, w.Transakcje, w.LiczbaLekow, w.MaxDostawcow,
       ROUND(w.SrOpoznienie, 1)                                        AS SrOpoznienieDni,
       ROUND(w.SrZmiennoscCeny, 3)                                     AS ZmiennoscCeny,
       ROUND(100 * w.MiesiaceWzrostu / NULLIF(w.MiesiaceZPorownaniem, 0), 1) AS ProcMiesiecyWzrostu,
       ROUND(w.NachylenieTrendu, 2)                                    AS NachylenieTrendu,
       ROUND(w.MedianaMiesieczna, 2)                                   AS MedianaMiesieczna,
       ROUND(100 * w.SredniUdzial, 2)                                  AS SredniUdzialProc,
       w.NajlepszaPozycja, w.RankOgolny
FROM   wyniki w
JOIN   Producent p ON p.ID = w.ProducentID
WHERE  w.Przychod > w.SredniPrzychod
AND    w.NachylenieTrendu > 0
AND    w.PercentylMarzy >= 0.25
AND    w.LiczbaLekow >= 3
ORDER  BY w.RankOgolny;