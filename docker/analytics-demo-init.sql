-- 仅使用合成订单。customer_email 与 internal_note 是负例字段，不含真实个人信息。
\getenv demo_reader_password ANALYTICS_DEMO_DB_PASSWORD
CREATE ROLE analytics_demo_reader LOGIN PASSWORD :'demo_reader_password';
CREATE SCHEMA demo;

CREATE TABLE demo.orders (
    order_id integer PRIMARY KEY,
    order_date date NOT NULL,
    region text NOT NULL,
    product text NOT NULL,
    status text NOT NULL CHECK (status IN ('paid', 'refunded', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    customer_email text NOT NULL,
    internal_note text NOT NULL
);

INSERT INTO demo.orders (order_id, order_date, region, product, status, amount, customer_email, internal_note) VALUES
    (1,  '2026-01-02', 'North', 'Atlas',  'paid',      100.00, 'synthetic-01@example.invalid', 'synthetic row 1'),
    (2,  '2026-01-10', 'North', 'Beacon', 'paid',      200.00, 'synthetic-02@example.invalid', 'synthetic row 2'),
    (3,  '2026-01-16', 'South', 'Atlas',  'paid',      150.00, 'synthetic-03@example.invalid', 'synthetic row 3'),
    (4,  '2026-01-21', 'South', 'Beacon', 'refunded',   50.00, 'synthetic-04@example.invalid', 'synthetic row 4'),
    (5,  '2026-01-25', 'West',  'Atlas',  'paid',       50.00, 'synthetic-05@example.invalid', 'synthetic row 5'),
    (6,  '2026-01-28', 'West',  'Beacon', 'cancelled',  30.00, 'synthetic-06@example.invalid', 'synthetic row 6'),
    (7,  '2026-01-29', 'North', 'Atlas',  'refunded',   20.00, 'synthetic-07@example.invalid', 'synthetic row 7'),
    (8,  '2026-01-30', 'West',  'Beacon', 'paid',       40.00, 'synthetic-08@example.invalid', 'synthetic row 8'),
    (9,  '2026-02-03', 'North', 'Atlas',  'paid',       75.00, 'synthetic-09@example.invalid', 'synthetic row 9'),
    (10, '2026-02-09', 'South', 'Beacon', 'refunded',   25.00, 'synthetic-10@example.invalid', 'synthetic row 10');

CREATE TABLE demo.internal_margin (
    order_id integer PRIMARY KEY,
    internal_margin numeric(12, 2) NOT NULL
);
INSERT INTO demo.internal_margin VALUES (1, 41.00);

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE TEMPORARY ON DATABASE analytics_test FROM PUBLIC;
GRANT CONNECT ON DATABASE analytics_test TO analytics_demo_reader;
GRANT USAGE ON SCHEMA demo TO analytics_demo_reader;
GRANT SELECT (order_id, order_date, region, product, status, amount) ON demo.orders TO analytics_demo_reader;
REVOKE CREATE ON SCHEMA demo FROM analytics_demo_reader;
REVOKE TEMPORARY ON DATABASE analytics_test FROM analytics_demo_reader;

ANALYZE demo.orders;
