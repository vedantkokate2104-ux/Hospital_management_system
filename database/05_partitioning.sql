-- =====================================================================
-- 05_partitioning.sql : table partitioning and performance comparison
-- (Lab 7: compare partitioned vs non-partitioned tables)
--
-- Patient vitals are recorded by bedside monitors every few minutes, so
-- this table grows fast. We store the same 600,000 rows twice:
--   vitals_flat         - one ordinary table
--   vitals_partitioned  - RANGE partitioned by year
-- and compare query plans and timings.
--
-- Run in psql:  \i database/05_partitioning.sql   (takes a few seconds)
-- =====================================================================
SET search_path TO hms, public;
\timing on

DROP TABLE IF EXISTS vitals_flat;
DROP TABLE IF EXISTS vitals_partitioned;

CREATE TABLE vitals_flat (
    reading_id  BIGINT       NOT NULL,
    patient_id  INT          NOT NULL,
    recorded_at TIMESTAMP    NOT NULL,
    pulse       SMALLINT,
    spo2        SMALLINT,
    systolic    SMALLINT,
    diastolic   SMALLINT
);

CREATE TABLE vitals_partitioned (
    reading_id  BIGINT       NOT NULL,
    patient_id  INT          NOT NULL,
    recorded_at TIMESTAMP    NOT NULL,
    pulse       SMALLINT,
    spo2        SMALLINT,
    systolic    SMALLINT,
    diastolic   SMALLINT
) PARTITION BY RANGE (recorded_at);

CREATE TABLE vitals_2023 PARTITION OF vitals_partitioned FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE vitals_2024 PARTITION OF vitals_partitioned FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE vitals_2025 PARTITION OF vitals_partitioned FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE vitals_2026 PARTITION OF vitals_partitioned FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE vitals_default PARTITION OF vitals_partitioned DEFAULT;

-- 600,000 synthetic readings spread over 2023-2026 for the 15 patients
INSERT INTO vitals_flat
SELECT g,
       1 + (g % 15),
       TIMESTAMP '2023-01-01' + g * INTERVAL '3.4 minutes',
       60 + (random() * 50)::int,
       90 + (random() * 10)::int,
       100 + (random() * 60)::int,
       60 + (random() * 40)::int
  FROM generate_series(1, 600000) AS g;

INSERT INTO vitals_partitioned SELECT * FROM vitals_flat;

-- same index on both (on a partitioned table it is created on every partition)
CREATE INDEX idx_vflat_patient_time ON vitals_flat        (patient_id, recorded_at);
CREATE INDEX idx_vpart_patient_time ON vitals_partitioned (patient_id, recorded_at);

ANALYZE vitals_flat;
ANALYZE vitals_partitioned;

-- How many rows landed in each partition?
SELECT tableoid::regclass AS partition, count(*) AS rows
  FROM vitals_partitioned
 GROUP BY 1 ORDER BY 1;

-- ---------------------------------------------------------------------
-- Query 1: average vitals for March 2025 (range scan)
-- The partitioned plan only touches vitals_2025 (partition pruning).
-- ---------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT avg(pulse), avg(spo2) FROM vitals_flat
 WHERE recorded_at >= '2025-03-01' AND recorded_at < '2025-04-01';

EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT avg(pulse), avg(spo2) FROM vitals_partitioned
 WHERE recorded_at >= '2025-03-01' AND recorded_at < '2025-04-01';

-- ---------------------------------------------------------------------
-- Query 2: one patient's readings in 2024 (index + pruning)
-- ---------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT max(systolic) FROM vitals_flat
 WHERE patient_id = 3 AND recorded_at >= '2024-01-01' AND recorded_at < '2025-01-01';

EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT max(systolic) FROM vitals_partitioned
 WHERE patient_id = 3 AND recorded_at >= '2024-01-01' AND recorded_at < '2025-01-01';

-- ---------------------------------------------------------------------
-- Maintenance benefit: dropping a whole year of old data
--   flat table        -> DELETE ... (scans and logs every row)
--   partitioned table -> DETACH / DROP one partition (instant)
-- ---------------------------------------------------------------------
BEGIN;
DELETE FROM vitals_flat WHERE recorded_at < '2024-01-01';
ROLLBACK;

BEGIN;
ALTER TABLE vitals_partitioned DETACH PARTITION vitals_2023;
ROLLBACK;

\timing off
