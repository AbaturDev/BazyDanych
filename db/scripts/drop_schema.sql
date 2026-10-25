BEGIN
    FOR t IN (SELECT table_name
                FROM user_tables
               WHERE table_name IN ('POZYCJASPRZEDAZY', 'SPRZEDAZ', 'POZYCJAZAMOWIENIA',
                                    'ZAMOWIENIE', 'DOSTAWCA', 'LEK', 'PRODUCENT')) LOOP
        EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
    END LOOP;
END;
/
