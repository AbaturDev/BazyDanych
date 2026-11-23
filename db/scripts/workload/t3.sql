SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 100

WITH sprzedaz_miesieczna AS (
    SELECT ps.LekID,
           TRUNC(s.DataSprzedazy, 'MM')                                 AS Miesiac,
           SUM(ps.Ilosc)                                                AS Opakowania,
           SUM(ps.Ilosc * ps.CenaSprzedazy * (1 - ps.Rabat / 100))      AS Przychod,
           COUNT(DISTINCT s.ID)                                         AS Transakcje
    FROM   PozycjaSprzedazy ps
    JOIN   Sprzedaz s ON s.ID = ps.SprzedazID
    GROUP  BY ps.LekID, TRUNC(s.DataSprzedazy, 'MM')
),
dostawy_miesieczne AS (
    SELECT pz.LekID,
           TRUNC(z.DataZamowienia, 'MM')                                AS Miesiac,
           SUM(pz.Ilosc)                                                AS Dostarczone,
           COUNT(DISTINCT z.DostawcaID)                                 AS Dostawcy
    FROM   PozycjaZamowienia pz
    JOIN   Zamowienie z ON z.ID = pz.ZamowienieID
    WHERE  z.Status = 'ZREALIZOWANE'
    GROUP  BY pz.LekID, TRUNC(z.DataZamowienia, 'MM')
),
szereg AS (
    SELECT NVL(sm.LekID, dm.LekID)                                      AS LekID,
           NVL(sm.Miesiac, dm.Miesiac)                                  AS Miesiac,
           NVL(sm.Opakowania, 0)                                        AS Opakowania,
           NVL(sm.Przychod, 0)                                          AS Przychod,
           NVL(sm.Transakcje, 0)                                        AS Transakcje,
           NVL(dm.Dostarczone, 0)                                       AS Dostarczone,
           NVL(dm.Dostawcy, 0)                                          AS Dostawcy
    FROM   sprzedaz_miesieczna sm
    FULL   OUTER JOIN dostawy_miesieczne dm
           ON dm.LekID = sm.LekID AND dm.Miesiac = sm.Miesiac
),
szereg_okno AS (
    SELECT sz.*,
           MONTHS_BETWEEN(Miesiac, DATE '2000-01-01')                   AS NrMsc,
           AVG(Opakowania) OVER (PARTITION BY LekID ORDER BY Miesiac
                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)  AS Ruchoma3m,
           LAG(Opakowania, 12) OVER (PARTITION BY LekID ORDER BY Miesiac)   AS OpakowaniaRokTemu,
           SUM(Dostarczone - Opakowania) OVER (PARTITION BY LekID ORDER BY Miesiac
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS SaldoNarastajace,
           RANK() OVER (PARTITION BY Miesiac ORDER BY Opakowania DESC)      AS RankMsc
    FROM   szereg sz
),
statystyki_leku AS (
    SELECT LekID,
           SUM(Opakowania)                                              AS Opakowania,
           SUM(Przychod)                                                AS Przychod,
           SUM(Transakcje)                                              AS Transakcje,
           SUM(Dostarczone)                                             AS Dostarczone,
           MAX(Dostawcy)                                                AS LiczbaDostawcow,
           COUNT(CASE WHEN Opakowania > 0 THEN 1 END)                   AS AktywneMiesiace,
           AVG(CASE WHEN Opakowania > 0 THEN Opakowania END)            AS SredniaMiesieczna,
           STDDEV(Opakowania)                                           AS OdchylenieMiesieczne,
           MAX(Opakowania)                                              AS MaxMiesiac,
           MIN(SaldoNarastajace)                                        AS MinSaldo,
           MIN(RankMsc)                                                 AS NajlepszaPozycjaMsc,
           SUM(CASE WHEN Opakowania > OpakowaniaRokTemu THEN 1 ELSE 0 END) AS MiesiaceWzrostu,
           SUM(CASE WHEN Miesiac >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -3)
                    THEN Opakowania ELSE 0 END)                         AS Ostatnie3m,
           CORR(Opakowania, Dostarczone)                                AS KorelacjaDostaw,
           REGR_SLOPE(Opakowania, NrMsc)                                AS NachylenieTrendu,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY Opakowania)      AS Mediana
    FROM   szereg_okno
    GROUP  BY LekID
),
polaczone AS (
    SELECT l.ID                    AS LekID,
           l.Nazwa                 AS Lek,
           p.ID                    AS ProducentID,
           p.Nazwa                 AS Producent,
           st.Opakowania,
           st.Przychod,
           st.Transakcje,
           st.Dostarczone,
           st.LiczbaDostawcow,
           st.AktywneMiesiace,
           st.SredniaMiesieczna,
           st.OdchylenieMiesieczne,
           st.MaxMiesiac,
           st.MinSaldo,
           st.NajlepszaPozycjaMsc,
           st.MiesiaceWzrostu,
           st.Ostatnie3m,
           st.KorelacjaDostaw,
           st.NachylenieTrendu,
           st.Mediana
    FROM   Lek l
    JOIN   Producent p ON p.ID = l.ProducentID
    JOIN   statystyki_leku st ON st.LekID = l.ID
),
analiza AS (
    SELECT po.*,
           AVG(Opakowania) OVER ()                                      AS SredniaSprzedazNaLek,
           SUM(Przychod) OVER (ORDER BY Przychod DESC
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             / SUM(Przychod) OVER ()                                    AS UdzialSkumulowany,
           ROW_NUMBER() OVER (PARTITION BY ProducentID ORDER BY Opakowania DESC) AS PozycjaWProducencie,
           PERCENT_RANK() OVER (ORDER BY Opakowania)                    AS Percentyl,
           NTILE(10) OVER (ORDER BY OdchylenieMiesieczne / NULLIF(SredniaMiesieczna, 0)) AS DecylZmiennosci,
           RANK() OVER (ORDER BY Opakowania DESC)                       AS RankOgolny
    FROM   polaczone po
)
SELECT /*+ GATHER_PLAN_STATISTICS */
       LekID, Lek, ProducentID, Producent, Opakowania,
       ROUND(Przychod, 2)                                               AS Przychod,
       Transakcje,
       ROUND(SredniaMiesieczna, 1)                                      AS SredniaMiesieczna,
       ROUND(Mediana, 1)                                                AS Mediana,
       ROUND(OdchylenieMiesieczne / NULLIF(SredniaMiesieczna, 0), 2)    AS WspolczynnikZmiennosci,
       MaxMiesiac,
       ROUND(100 * (Ostatnie3m / 3 - SredniaMiesieczna) / NULLIF(SredniaMiesieczna, 0), 1) AS TrendProc,
       ROUND(NachylenieTrendu, 3)                                       AS NachylenieTrendu,
       ROUND(KorelacjaDostaw, 2)                                        AS KorelacjaDostaw,
       ROUND(Opakowania / NULLIF(Dostarczone, 0), 2)                    AS Rotacja,
       MinSaldo, LiczbaDostawcow, NajlepszaPozycjaMsc,
       ROUND(100 * MiesiaceWzrostu / NULLIF(AktywneMiesiace, 0), 1)     AS ProcMiesiecyWzrostu,
       ROUND(100 * UdzialSkumulowany, 1)                                AS UdzialSkumulowanyProc,
       CASE WHEN UdzialSkumulowany <= 0.80 THEN 'A'
            WHEN UdzialSkumulowany <= 0.95 THEN 'B' ELSE 'C' END        AS KlasaABC,
       DecylZmiennosci, PozycjaWProducencie, RankOgolny
FROM   analiza
WHERE  Opakowania > SredniaSprzedazNaLek
AND    UdzialSkumulowany <= 0.95
AND    AktywneMiesiace >= 6
AND    PozycjaWProducencie <= 5
ORDER  BY Opakowania DESC, Lek;
