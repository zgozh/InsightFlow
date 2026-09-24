CREATE EXTENSION pg_stat_statements;
GRANT USAGE ON SCHEMA public TO analytics_tester, analytics_reader, analytics_demo_observer;
GRANT SELECT ON public.pg_stat_statements TO analytics_demo_observer;
