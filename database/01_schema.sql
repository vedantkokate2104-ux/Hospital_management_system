-- =====================================================================
-- Hospital Management System
-- 01_schema.sql : types, domains, tables, constraints, indexes
-- Target: PostgreSQL 14+
--
-- ADBMS topics shown here
--   * EER specialization / generalization  -> staff  <- doctors, nurses
--     implemented with PostgreSQL table INHERITANCE (object-relational)
--   * User defined types                   -> address_t (composite), ENUMs
--   * Domains with constraints             -> phone_no, email_addr
--   * Collection types                     -> patients.allergies TEXT[]
--   * Temporal constraint                  -> admissions.stay DATERANGE with
--                                             an EXCLUDE constraint so a room
--                                             can never be double-booked
--   * Semi-structured data                 -> medical_records JSONB + XML
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS btree_gist;   -- needed for the EXCLUDE constraint

DROP SCHEMA IF EXISTS hms CASCADE;
CREATE SCHEMA hms;
SET search_path TO hms, public;

-- ---------------------------------------------------------------------
-- Domains and user defined types
-- ---------------------------------------------------------------------
CREATE DOMAIN phone_no   AS VARCHAR(15)  CHECK (VALUE ~ '^\+?[0-9]{10,13}$');
CREATE DOMAIN email_addr AS VARCHAR(100) CHECK (VALUE ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$');

CREATE TYPE gender_t         AS ENUM ('Male', 'Female', 'Other');
CREATE TYPE blood_group_t    AS ENUM ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-');
CREATE TYPE room_type_t      AS ENUM ('General', 'Semi-Private', 'Private', 'ICU');
CREATE TYPE room_status_t    AS ENUM ('Available', 'Occupied', 'Maintenance');
CREATE TYPE appt_status_t    AS ENUM ('Scheduled', 'Completed', 'Cancelled');
CREATE TYPE payment_status_t AS ENUM ('Unpaid', 'Paid');
CREATE TYPE shift_t          AS ENUM ('Morning', 'Evening', 'Night');

-- Composite (structured) type used as a column type in patients
CREATE TYPE address_t AS (
    street  VARCHAR(100),
    city    VARCHAR(50),
    state   VARCHAR(50),
    pincode CHAR(6)
);

-- ---------------------------------------------------------------------
-- Departments
-- ---------------------------------------------------------------------
CREATE TABLE departments (
    dept_id  SERIAL PRIMARY KEY,
    name     VARCHAR(100) NOT NULL UNIQUE,
    floor_no SMALLINT     NOT NULL CHECK (floor_no BETWEEN 0 AND 20),
    phone    phone_no
);

-- ---------------------------------------------------------------------
-- Staff hierarchy (generalization / specialization)
--
--            staff  (superclass: common attributes)
--           /     \
--      doctors   nurses   (subclasses: specific attributes)
--
-- NOT NULL and CHECK constraints are inherited by the children,
-- PRIMARY KEY / UNIQUE / FOREIGN KEY constraints are NOT, so each
-- child declares its own. All three tables share the staff_id
-- sequence, so ids are unique across the whole hierarchy (disjoint).
-- ---------------------------------------------------------------------
CREATE TABLE staff (
    staff_id   SERIAL PRIMARY KEY,
    first_name VARCHAR(50)   NOT NULL,
    last_name  VARCHAR(50)   NOT NULL,
    phone      phone_no      NOT NULL,
    email      email_addr    NOT NULL,
    hire_date  DATE          NOT NULL DEFAULT CURRENT_DATE,
    salary     NUMERIC(10,2) NOT NULL CHECK (salary > 0),
    dept_id    INT           NOT NULL REFERENCES departments(dept_id)
);

CREATE TABLE doctors (
    specialization   VARCHAR(100)  NOT NULL,
    license_no       VARCHAR(20)   NOT NULL,
    consultation_fee NUMERIC(10,2) NOT NULL DEFAULT 500 CHECK (consultation_fee >= 0),
    PRIMARY KEY (staff_id),
    UNIQUE (email),
    UNIQUE (license_no),
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
) INHERITS (staff);

CREATE TABLE nurses (
    shift shift_t     NOT NULL DEFAULT 'Morning',
    ward  VARCHAR(50) NOT NULL,
    PRIMARY KEY (staff_id),
    UNIQUE (email),
    FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
) INHERITS (staff);

-- ---------------------------------------------------------------------
-- Patients
-- ---------------------------------------------------------------------
CREATE TABLE patients (
    patient_id    SERIAL PRIMARY KEY,
    first_name    VARCHAR(50) NOT NULL,
    last_name     VARCHAR(50) NOT NULL,
    dob           DATE        NOT NULL,
    gender        gender_t    NOT NULL,
    blood_group   blood_group_t,
    phone         phone_no    NOT NULL,
    email         email_addr,
    address       address_t,
    allergies     TEXT[]      NOT NULL DEFAULT '{}',
    registered_on TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_patient_name        ON patients (last_name, first_name);
CREATE INDEX idx_patient_email_lower ON patients (lower(email));        -- expression index
CREATE INDEX idx_patient_allergies   ON patients USING gin (allergies); -- array search

-- ---------------------------------------------------------------------
-- Rooms
-- ---------------------------------------------------------------------
CREATE TABLE rooms (
    room_id      SERIAL PRIMARY KEY,
    room_number  VARCHAR(10)   NOT NULL UNIQUE,
    room_type    room_type_t   NOT NULL,
    daily_charge NUMERIC(10,2) NOT NULL CHECK (daily_charge > 0),
    status       room_status_t NOT NULL DEFAULT 'Available'
);

-- ---------------------------------------------------------------------
-- Appointments (out-patient visits)
-- ---------------------------------------------------------------------
CREATE TABLE appointments (
    appointment_id   SERIAL PRIMARY KEY,
    patient_id       INT           NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    doctor_id        INT           NOT NULL REFERENCES doctors(staff_id),
    appointment_time TIMESTAMP     NOT NULL,
    reason           VARCHAR(255),
    status           appt_status_t NOT NULL DEFAULT 'Scheduled',
    CONSTRAINT uq_doctor_slot UNIQUE (doctor_id, appointment_time)
);

CREATE INDEX idx_appt_time ON appointments (appointment_time);

-- ---------------------------------------------------------------------
-- Admissions (in-patient stays)
-- stay is a generated DATERANGE; the EXCLUDE constraint makes it
-- impossible for two stays in the same room to overlap in time.
-- ---------------------------------------------------------------------
CREATE TABLE admissions (
    admission_id   SERIAL PRIMARY KEY,
    patient_id     INT  NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    room_id        INT  NOT NULL REFERENCES rooms(room_id),
    doctor_id      INT  NOT NULL REFERENCES doctors(staff_id),
    admit_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    discharge_date DATE,
    diagnosis      VARCHAR(255),
    stay DATERANGE GENERATED ALWAYS AS (daterange(admit_date, discharge_date, '[)')) STORED,
    CONSTRAINT chk_discharge CHECK (discharge_date IS NULL OR discharge_date >= admit_date),
    CONSTRAINT no_room_overlap EXCLUDE USING gist (room_id WITH =, stay WITH &&)
);

-- a patient can have at most one open admission
CREATE UNIQUE INDEX uq_one_active_admission ON admissions (patient_id) WHERE discharge_date IS NULL;

-- ---------------------------------------------------------------------
-- Pharmacy
-- ---------------------------------------------------------------------
CREATE TABLE medicines (
    medicine_id   SERIAL PRIMARY KEY,
    name          VARCHAR(100)  NOT NULL UNIQUE,
    unit_price    NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0),
    stock_qty     INT           NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    reorder_level INT           NOT NULL DEFAULT 20
);

CREATE TABLE prescriptions (
    prescription_id SERIAL PRIMARY KEY,
    appointment_id  INT         NOT NULL REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    medicine_id     INT         NOT NULL REFERENCES medicines(medicine_id),
    dosage          VARCHAR(50) NOT NULL,
    quantity        INT         NOT NULL CHECK (quantity > 0),
    duration_days   INT         NOT NULL CHECK (duration_days > 0)
);

-- ---------------------------------------------------------------------
-- Bills: exactly one of appointment_id / admission_id is set
-- ---------------------------------------------------------------------
CREATE TABLE bills (
    bill_id        SERIAL PRIMARY KEY,
    patient_id     INT              NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    appointment_id INT UNIQUE       REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    admission_id   INT UNIQUE       REFERENCES admissions(admission_id) ON DELETE CASCADE,
    amount         NUMERIC(10,2)    NOT NULL CHECK (amount >= 0),
    bill_date      DATE             NOT NULL DEFAULT CURRENT_DATE,
    payment_status payment_status_t NOT NULL DEFAULT 'Unpaid',
    paid_on        DATE,
    CONSTRAINT chk_bill_source CHECK (num_nonnulls(appointment_id, admission_id) = 1)
);

-- partial index: only unpaid bills are looked up often
CREATE INDEX idx_bills_unpaid ON bills (patient_id) WHERE payment_status = 'Unpaid';

-- ---------------------------------------------------------------------
-- Medical records: semi-structured data
--   details     JSONB  (lab values, vitals ... shape differs per record)
--   summary_xml XML    (discharge summaries exchanged with other systems)
-- ---------------------------------------------------------------------
CREATE TABLE medical_records (
    record_id   SERIAL PRIMARY KEY,
    patient_id  INT         NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    doctor_id   INT         REFERENCES doctors(staff_id),
    record_type VARCHAR(30) NOT NULL,
    recorded_at TIMESTAMP   NOT NULL DEFAULT now(),
    details     JSONB       NOT NULL DEFAULT '{}',
    summary_xml XML
);

CREATE INDEX idx_records_details ON medical_records USING gin (details jsonb_path_ops);

-- ---------------------------------------------------------------------
-- Audit log, filled by triggers (active database)
-- ---------------------------------------------------------------------
CREATE TABLE audit_log (
    log_id     BIGSERIAL PRIMARY KEY,
    table_name TEXT      NOT NULL,
    operation  TEXT      NOT NULL,
    row_id     TEXT,
    changed_by TEXT      NOT NULL DEFAULT current_user,
    changed_at TIMESTAMP NOT NULL DEFAULT now(),
    old_data   JSONB,
    new_data   JSONB
);
