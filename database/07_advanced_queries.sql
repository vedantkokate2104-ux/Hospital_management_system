-- =====================================================================
-- 07_advanced_queries.sql : object-relational queries, analytics,
-- query optimization and transactions
-- Run after the sample data:  \i database/07_advanced_queries.sql
-- =====================================================================
SET search_path TO hms, public;

-- ---------------------------------------------------------------------
-- A. Inheritance (type hierarchy and type extents)
-- ---------------------------------------------------------------------

-- Querying the superclass returns rows from every subclass
SELECT tableoid::regclass AS stored_in, staff_id, first_name, last_name, salary
  FROM staff ORDER BY staff_id;

-- ONLY restricts to rows stored in the parent table itself (none here)
SELECT count(*) AS rows_only_in_staff FROM ONLY staff;

-- Average salary per subclass
SELECT tableoid::regclass AS role, count(*), round(avg(salary)) AS avg_salary
  FROM staff GROUP BY 1;

-- An UPDATE on the parent reaches the children too (5% raise, rolled back)
BEGIN;
UPDATE staff SET salary = salary * 1.05 WHERE dept_id = 2;
SELECT staff_id, first_name, salary FROM staff WHERE dept_id = 2;
ROLLBACK;

-- ---------------------------------------------------------------------
-- B. Composite types and arrays
-- ---------------------------------------------------------------------
SELECT first_name, (address).city, (address).pincode FROM patients WHERE (address).city <> 'Mumbai';

-- patients allergic to Penicillin (uses the GIN index on allergies)
SELECT first_name, last_name, allergies FROM patients WHERE allergies @> ARRAY['Penicillin'];

-- ---------------------------------------------------------------------
-- C. Analytics: CTEs and window functions
-- ---------------------------------------------------------------------

-- Rank doctors by revenue inside their department
WITH doctor_revenue AS (
    SELECT d.staff_id, d.first_name || ' ' || d.last_name AS doctor, dep.name AS department,
           COALESCE(sum(b.amount), 0) AS revenue
      FROM doctors d
      JOIN departments dep ON dep.dept_id = d.dept_id
      LEFT JOIN appointments a ON a.doctor_id = d.staff_id
      LEFT JOIN bills b ON b.appointment_id = a.appointment_id
     GROUP BY d.staff_id, doctor, department
)
SELECT department, doctor, revenue,
       RANK() OVER (PARTITION BY department ORDER BY revenue DESC) AS rank_in_dept,
       round(100.0 * revenue / NULLIF(sum(revenue) OVER (), 0), 1) AS pct_of_total
  FROM doctor_revenue
 ORDER BY department, rank_in_dept;

-- Running total of billing by date
SELECT bill_date, sum(amount) AS day_total,
       sum(sum(amount)) OVER (ORDER BY bill_date) AS running_total
  FROM bills GROUP BY bill_date ORDER BY bill_date;

-- Days between consecutive visits of each patient (LAG)
SELECT patient_id, appointment_time::date AS visit,
       appointment_time::date - LAG(appointment_time::date) OVER (PARTITION BY patient_id ORDER BY appointment_time) AS days_since_last
  FROM appointments
 WHERE status = 'Completed'
 ORDER BY patient_id, visit;

-- Recursive CTE: room occupancy for each of the last 14 days
WITH RECURSIVE days(d) AS (
    SELECT CURRENT_DATE - 13
    UNION ALL
    SELECT d + 1 FROM days WHERE d < CURRENT_DATE
)
SELECT d AS day, count(a.admission_id) AS occupied_rooms
  FROM days
  LEFT JOIN admissions a ON a.stay @> d
 GROUP BY d ORDER BY d;

-- Stored function returning a table (uses an explicit cursor)
SELECT * FROM fn_doctor_workload(CURRENT_DATE - 90, CURRENT_DATE + 30);

-- ---------------------------------------------------------------------
-- D. Query cost and optimization
-- ---------------------------------------------------------------------

-- Index scan vs sequential scan: compare the plans
EXPLAIN ANALYZE SELECT * FROM appointments WHERE appointment_time >= CURRENT_DATE;

SET enable_indexscan = off; SET enable_bitmapscan = off;
EXPLAIN ANALYZE SELECT * FROM appointments WHERE appointment_time >= CURRENT_DATE;
RESET enable_indexscan; RESET enable_bitmapscan;

-- Expression index is only used when the query uses the same expression
EXPLAIN SELECT * FROM patients WHERE lower(email) = 'rahul.sharma@gmail.com';

-- Join order and join algorithm chosen by the planner
EXPLAIN ANALYZE
SELECT p.first_name, d.last_name, b.amount
  FROM bills b
  JOIN appointments a ON a.appointment_id = b.appointment_id
  JOIN patients p     ON p.patient_id     = a.patient_id
  JOIN doctors d      ON d.staff_id       = a.doctor_id
 WHERE b.payment_status = 'Unpaid';

-- ---------------------------------------------------------------------
-- E. Transactions, constraints and concurrency
-- ---------------------------------------------------------------------

-- Savepoint: keep the first change, undo the failed second one
BEGIN;
UPDATE medicines SET unit_price = unit_price + 1 WHERE medicine_id = 1;
SAVEPOINT before_bad_update;
DO $$ BEGIN
    UPDATE medicines SET stock_qty = -5 WHERE medicine_id = 2;   -- violates CHECK
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'CHECK constraint stopped negative stock';
END $$;
ROLLBACK TO SAVEPOINT before_bad_update;
SELECT medicine_id, unit_price FROM medicines WHERE medicine_id = 1;
ROLLBACK;

-- The EXCLUDE constraint rejects an overlapping booking of room I-402
DO $$ BEGIN
    INSERT INTO admissions (patient_id, room_id, doctor_id, admit_date)
    VALUES (1, 9, 1, CURRENT_DATE);
EXCEPTION WHEN exclusion_violation THEN
    RAISE NOTICE 'Room 9 is already booked for that period';
END $$;

-- Trigger rejects a prescription larger than the stock
DO $$ BEGIN
    INSERT INTO prescriptions (appointment_id, medicine_id, dosage, quantity, duration_days)
    VALUES (17, 9, '1 daily', 1000, 30);
EXCEPTION WHEN raise_exception THEN
    RAISE NOTICE 'Trigger said: %', SQLERRM;
END $$;

-- Isolation level for a consistent report (all reads see one snapshot)
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT sum(amount) FROM bills;
SELECT sum(total_billed) FROM v_patient_billing_summary;
COMMIT;

-- ---------------------------------------------------------------------
-- F. Security: a read-only role for the reception desk
-- ---------------------------------------------------------------------
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hms_reception') THEN
        CREATE ROLE hms_reception NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA hms TO hms_reception;
GRANT SELECT ON v_doctor_directory, v_upcoming_appointments TO hms_reception;
GRANT SELECT, INSERT ON patients, appointments TO hms_reception;
