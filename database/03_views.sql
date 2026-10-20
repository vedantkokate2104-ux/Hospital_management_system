-- =====================================================================
-- 03_views.sql : views and a materialized view used by the app
-- =====================================================================
SET search_path TO hms, public;

-- Every staff member with their role. tableoid tells which table in the
-- inheritance hierarchy (type extent) the row really lives in.
CREATE OR REPLACE VIEW v_all_staff AS
SELECT s.staff_id,
       s.tableoid::regclass::text   AS role_table,
       CASE s.tableoid::regclass::text
            WHEN 'doctors' THEN 'Doctor'
            WHEN 'nurses'  THEN 'Nurse'
            ELSE 'Staff' END        AS role,
       s.first_name || ' ' || s.last_name AS full_name,
       d.name AS department,
       s.phone, s.email, s.hire_date, s.salary
  FROM staff s
  JOIN departments d ON d.dept_id = s.dept_id;

CREATE OR REPLACE VIEW v_doctor_directory AS
SELECT doc.staff_id AS doctor_id,
       'Dr. ' || doc.first_name || ' ' || doc.last_name AS doctor_name,
       doc.specialization, dep.name AS department, dep.floor_no,
       doc.consultation_fee, doc.phone, doc.email
  FROM doctors doc
  JOIN departments dep ON dep.dept_id = doc.dept_id;

CREATE OR REPLACE VIEW v_upcoming_appointments AS
SELECT a.appointment_id, a.appointment_time,
       p.patient_id, p.first_name || ' ' || p.last_name AS patient_name,
       d.staff_id AS doctor_id, 'Dr. ' || d.first_name || ' ' || d.last_name AS doctor_name,
       d.specialization, a.reason
  FROM appointments a
  JOIN patients p ON p.patient_id = a.patient_id
  JOIN doctors  d ON d.staff_id   = a.doctor_id
 WHERE a.status = 'Scheduled'
   AND a.appointment_time >= CURRENT_DATE;

CREATE OR REPLACE VIEW v_current_admissions AS
SELECT ad.admission_id, ad.admit_date,
       CURRENT_DATE - ad.admit_date                 AS days_admitted,
       p.patient_id, p.first_name || ' ' || p.last_name AS patient_name,
       r.room_number, r.room_type,
       'Dr. ' || d.first_name || ' ' || d.last_name AS doctor_name,
       ad.diagnosis,
       fn_admission_charge(ad.admission_id)         AS charge_so_far
  FROM admissions ad
  JOIN patients p ON p.patient_id = ad.patient_id
  JOIN rooms    r ON r.room_id    = ad.room_id
  JOIN doctors  d ON d.staff_id   = ad.doctor_id
 WHERE ad.discharge_date IS NULL;

CREATE OR REPLACE VIEW v_patient_billing_summary AS
SELECT p.patient_id,
       p.first_name || ' ' || p.last_name                                    AS patient_name,
       count(b.bill_id)                                                      AS bills,
       COALESCE(sum(b.amount), 0)                                            AS total_billed,
       COALESCE(sum(b.amount) FILTER (WHERE b.payment_status = 'Paid'), 0)   AS total_paid,
       COALESCE(sum(b.amount) FILTER (WHERE b.payment_status = 'Unpaid'), 0) AS outstanding
  FROM patients p
  LEFT JOIN bills b ON b.patient_id = p.patient_id
 GROUP BY p.patient_id, p.first_name, p.last_name;

CREATE OR REPLACE VIEW v_low_stock AS
SELECT medicine_id, name, stock_qty, reorder_level
  FROM medicines
 WHERE stock_qty < reorder_level;

-- Materialized view: monthly revenue split by OPD / IPD.
-- Stored on disk, refreshed on demand (REFRESH MATERIALIZED VIEW).
CREATE MATERIALIZED VIEW mv_monthly_revenue AS
SELECT date_trunc('month', bill_date)::date                               AS month,
       sum(amount) FILTER (WHERE appointment_id IS NOT NULL)              AS opd_revenue,
       sum(amount) FILTER (WHERE admission_id  IS NOT NULL)               AS ipd_revenue,
       sum(amount)                                                        AS total_revenue,
       sum(amount) FILTER (WHERE payment_status = 'Paid')                 AS collected
  FROM bills
 GROUP BY 1;

-- a unique index allows REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX uq_mv_monthly_revenue ON mv_monthly_revenue (month);
