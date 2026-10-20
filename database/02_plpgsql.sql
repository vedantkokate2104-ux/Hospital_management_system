-- =====================================================================
-- 02_plpgsql.sql : functions, procedures, cursors, exception handling
--                  and triggers (PL/pgSQL, PostgreSQL's PL/SQL)
-- =====================================================================
SET search_path TO hms, public;

-- ---------------------------------------------------------------------
-- FUNCTION: age of a patient in years
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_patient_age(p_dob DATE)
RETURNS INT
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN EXTRACT(YEAR FROM age(CURRENT_DATE, p_dob))::INT;
END;
$$;

-- ---------------------------------------------------------------------
-- FUNCTION: amount to charge for an admission
--   room charge for every day stayed (minimum 1) + doctor's fee
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_admission_charge(p_admission_id INT, p_until DATE DEFAULT CURRENT_DATE)
RETURNS NUMERIC
LANGUAGE plpgsql AS $$
DECLARE
    v_days   INT;
    v_rate   rooms.daily_charge%TYPE;
    v_fee    doctors.consultation_fee%TYPE;
BEGIN
    SELECT GREATEST(COALESCE(a.discharge_date, p_until) - a.admit_date, 1),
           r.daily_charge,
           d.consultation_fee
      INTO v_days, v_rate, v_fee
      FROM admissions a
      JOIN rooms   r ON r.room_id  = a.room_id
      JOIN doctors d ON d.staff_id = a.doctor_id
     WHERE a.admission_id = p_admission_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Admission % does not exist', p_admission_id;
    END IF;

    RETURN v_days * v_rate + v_fee;
END;
$$;

-- ---------------------------------------------------------------------
-- PROCEDURE: admit a patient (one transaction)
--   locks the room row, checks it is free, creates the admission and
--   marks the room occupied. Constraint errors are turned into
--   readable messages in the EXCEPTION block.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_admit_patient(
    p_patient_id   INT,
    p_room_id      INT,
    p_doctor_id    INT,
    p_diagnosis    VARCHAR,
    p_admit_date   DATE DEFAULT CURRENT_DATE,
    INOUT p_admission_id INT DEFAULT NULL
)
LANGUAGE plpgsql AS $$
DECLARE
    v_status rooms.status%TYPE;
BEGIN
    SELECT status INTO v_status FROM rooms WHERE room_id = p_room_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Room % does not exist', p_room_id;
    ELSIF v_status <> 'Available' THEN
        RAISE EXCEPTION 'Room % is not available (status: %)', p_room_id, v_status;
    END IF;

    BEGIN
        INSERT INTO admissions (patient_id, room_id, doctor_id, admit_date, diagnosis)
        VALUES (p_patient_id, p_room_id, p_doctor_id, p_admit_date, p_diagnosis)
        RETURNING admission_id INTO p_admission_id;
    EXCEPTION
        WHEN unique_violation THEN
            RAISE EXCEPTION 'Patient % is already admitted', p_patient_id;
        WHEN exclusion_violation THEN
            RAISE EXCEPTION 'Room % is already booked for that period', p_room_id;
        WHEN foreign_key_violation THEN
            RAISE EXCEPTION 'Unknown patient or doctor';
    END;

    UPDATE rooms SET status = 'Occupied' WHERE room_id = p_room_id;
END;
$$;

-- ---------------------------------------------------------------------
-- PROCEDURE: discharge a patient
--   closes the admission, frees the room and generates the bill
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_discharge_patient(
    p_admission_id   INT,
    p_discharge_date DATE DEFAULT CURRENT_DATE
)
LANGUAGE plpgsql AS $$
DECLARE
    v_adm admissions%ROWTYPE;
BEGIN
    SELECT * INTO v_adm FROM admissions WHERE admission_id = p_admission_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Admission % does not exist', p_admission_id;
    ELSIF v_adm.discharge_date IS NOT NULL THEN
        RAISE EXCEPTION 'Admission % was already discharged on %', p_admission_id, v_adm.discharge_date;
    ELSIF p_discharge_date < v_adm.admit_date THEN
        RAISE EXCEPTION 'Discharge date cannot be before admit date (%)', v_adm.admit_date;
    END IF;

    UPDATE admissions SET discharge_date = p_discharge_date WHERE admission_id = p_admission_id;
    UPDATE rooms      SET status = 'Available'              WHERE room_id = v_adm.room_id;

    INSERT INTO bills (patient_id, admission_id, amount, bill_date)
    VALUES (v_adm.patient_id, p_admission_id, fn_admission_charge(p_admission_id), p_discharge_date);
END;
$$;

-- ---------------------------------------------------------------------
-- FUNCTION with an EXPLICIT CURSOR: workload report per doctor
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_doctor_workload(p_from DATE, p_to DATE)
RETURNS TABLE (
    doctor_id   INT,
    doctor_name TEXT,
    specialization VARCHAR,
    total       BIGINT,
    completed   BIGINT,
    cancelled   BIGINT,
    revenue     NUMERIC
)
LANGUAGE plpgsql AS $$
DECLARE
    cur_doctors CURSOR FOR
        SELECT d.staff_id, d.first_name || ' ' || d.last_name AS name, d.specialization
          FROM doctors d
         ORDER BY d.last_name;
    rec RECORD;
BEGIN
    OPEN cur_doctors;
    LOOP
        FETCH cur_doctors INTO rec;
        EXIT WHEN NOT FOUND;

        doctor_id      := rec.staff_id;
        doctor_name    := 'Dr. ' || rec.name;
        specialization := rec.specialization;

        SELECT count(*),
               count(*) FILTER (WHERE a.status = 'Completed'),
               count(*) FILTER (WHERE a.status = 'Cancelled'),
               COALESCE(sum(b.amount), 0)
          INTO total, completed, cancelled, revenue
          FROM appointments a
          LEFT JOIN bills b ON b.appointment_id = a.appointment_id
         WHERE a.doctor_id = rec.staff_id
           AND a.appointment_time::date BETWEEN p_from AND p_to;

        RETURN NEXT;
    END LOOP;
    CLOSE cur_doctors;
END;
$$;

-- ---------------------------------------------------------------------
-- PROCEDURE with an UPDATABLE CURSOR: restock every medicine that is
-- below its reorder level (UPDATE ... WHERE CURRENT OF)
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_restock_low_medicines(
    p_quantity INT,
    INOUT p_restocked INT DEFAULT 0
)
LANGUAGE plpgsql AS $$
DECLARE
    cur_low CURSOR FOR
        SELECT medicine_id, name, stock_qty FROM medicines
         WHERE stock_qty < reorder_level
           FOR UPDATE;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Restock quantity must be positive';
    END IF;

    p_restocked := 0;
    FOR m IN cur_low LOOP
        UPDATE medicines SET stock_qty = stock_qty + p_quantity WHERE CURRENT OF cur_low;
        RAISE NOTICE 'Restocked % (was %)', m.name, m.stock_qty;
        p_restocked := p_restocked + 1;
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------
-- FUNCTION: full patient record as XML (SQL/XML publishing functions)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_patient_xml(p_patient_id INT)
RETURNS XML
LANGUAGE sql STABLE AS $$
    SELECT xmlelement(name patient,
             xmlattributes(p.patient_id AS id),
             xmlforest(p.first_name, p.last_name, p.dob, p.gender, p.blood_group, p.phone),
             xmlelement(name appointments,
               (SELECT xmlagg(xmlelement(name appointment,
                         xmlattributes(a.appointment_id AS id, a.status AS status),
                         xmlforest(a.appointment_time AS time,
                                   'Dr. ' || d.first_name || ' ' || d.last_name AS doctor,
                                   a.reason))
                        ORDER BY a.appointment_time)
                  FROM appointments a JOIN doctors d ON d.staff_id = a.doctor_id
                 WHERE a.patient_id = p.patient_id)),
             xmlelement(name admissions,
               (SELECT xmlagg(xmlelement(name admission,
                         xmlattributes(ad.admission_id AS id),
                         xmlforest(ad.admit_date, ad.discharge_date, ad.diagnosis))
                        ORDER BY ad.admit_date)
                  FROM admissions ad WHERE ad.patient_id = p.patient_id)))
      FROM patients p
     WHERE p.patient_id = p_patient_id;
$$;

-- ---------------------------------------------------------------------
-- FUNCTION: full patient record as JSON
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_patient_json(p_patient_id INT)
RETURNS JSONB
LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_object(
             'patient_id',  p.patient_id,
             'name',        p.first_name || ' ' || p.last_name,
             'dob',         p.dob,
             'gender',      p.gender,
             'blood_group', p.blood_group,
             'address',     to_jsonb(p.address),
             'allergies',   to_jsonb(p.allergies),
             'appointments', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                                 'id', a.appointment_id, 'time', a.appointment_time,
                                 'doctor_id', a.doctor_id, 'status', a.status,
                                 'reason', a.reason) ORDER BY a.appointment_time)
                               FROM appointments a WHERE a.patient_id = p.patient_id), '[]'),
             'medical_records', COALESCE((SELECT jsonb_agg(jsonb_build_object(
                                 'type', m.record_type, 'recorded_at', m.recorded_at,
                                 'details', m.details) ORDER BY m.recorded_at)
                               FROM medical_records m WHERE m.patient_id = p.patient_id), '[]'))
      FROM patients p
     WHERE p.patient_id = p_patient_id;
$$;

-- =====================================================================
-- TRIGGERS (active database rules)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Appointments must be within OPD hours (08:00 - 20:00) and a
--    cancelled/completed appointment cannot go back to Scheduled.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_validate_appointment()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.appointment_time::time NOT BETWEEN '08:00' AND '20:00' THEN
        RAISE EXCEPTION 'Appointments are only allowed between 08:00 and 20:00';
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.status <> 'Scheduled' AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION 'Appointment % is already % and cannot be changed', OLD.appointment_id, OLD.status;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_appointment
BEFORE INSERT OR UPDATE ON appointments
FOR EACH ROW EXECUTE FUNCTION trg_fn_validate_appointment();

-- ---------------------------------------------------------------------
-- 2. Prescribing a medicine reduces stock; fails if stock is short.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_prescription_stock()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_stock  medicines.stock_qty%TYPE;
    v_name   medicines.name%TYPE;
    v_status appointments.status%TYPE;
BEGIN
    SELECT status INTO v_status FROM appointments WHERE appointment_id = NEW.appointment_id;
    IF v_status = 'Cancelled' THEN
        RAISE EXCEPTION 'Cannot prescribe on a cancelled appointment';
    END IF;

    SELECT stock_qty, name INTO v_stock, v_name
      FROM medicines WHERE medicine_id = NEW.medicine_id FOR UPDATE;

    IF v_stock < NEW.quantity THEN
        RAISE EXCEPTION 'Insufficient stock for %: % available, % requested', v_name, v_stock, NEW.quantity;
    END IF;

    UPDATE medicines SET stock_qty = stock_qty - NEW.quantity WHERE medicine_id = NEW.medicine_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prescription_stock
BEFORE INSERT ON prescriptions
FOR EACH ROW EXECUTE FUNCTION trg_fn_prescription_stock();

-- ---------------------------------------------------------------------
-- 3. Completing an appointment generates its bill automatically:
--    consultation fee + cost of prescribed medicines.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_appointment_bill()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_fee   NUMERIC;
    v_meds  NUMERIC;
BEGIN
    SELECT consultation_fee INTO v_fee FROM doctors WHERE staff_id = NEW.doctor_id;

    SELECT COALESCE(sum(p.quantity * m.unit_price), 0) INTO v_meds
      FROM prescriptions p JOIN medicines m ON m.medicine_id = p.medicine_id
     WHERE p.appointment_id = NEW.appointment_id;

    INSERT INTO bills (patient_id, appointment_id, amount, bill_date)
    VALUES (NEW.patient_id, NEW.appointment_id, v_fee + v_meds, NEW.appointment_time::date);

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_appointment_bill
AFTER UPDATE OF status ON appointments
FOR EACH ROW
WHEN (NEW.status = 'Completed' AND OLD.status <> 'Completed')
EXECUTE FUNCTION trg_fn_appointment_bill();

-- ---------------------------------------------------------------------
-- 4. Marking a bill paid stamps the payment date.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_bill_paid()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.payment_status = 'Paid' AND OLD.payment_status = 'Unpaid' THEN
        NEW.paid_on := COALESCE(NEW.paid_on, CURRENT_DATE);
    ELSIF NEW.payment_status = 'Unpaid' THEN
        NEW.paid_on := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_bill_paid
BEFORE UPDATE OF payment_status ON bills
FOR EACH ROW EXECUTE FUNCTION trg_fn_bill_paid();

-- ---------------------------------------------------------------------
-- 5. Generic audit trigger: stores old/new row as JSONB.
--    TG_ARGV[0] is the primary key column of the audited table.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_fn_audit()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_old JSONB := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    v_new JSONB := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
BEGIN
    INSERT INTO audit_log (table_name, operation, row_id, old_data, new_data)
    VALUES (TG_TABLE_NAME, TG_OP,
            COALESCE(v_new, v_old) ->> TG_ARGV[0],
            v_old, v_new);
    RETURN NULL;   -- AFTER trigger: return value is ignored
END;
$$;

CREATE TRIGGER trg_audit_patients
AFTER INSERT OR UPDATE OR DELETE ON patients
FOR EACH ROW EXECUTE FUNCTION trg_fn_audit('patient_id');

CREATE TRIGGER trg_audit_admissions
AFTER INSERT OR UPDATE OR DELETE ON admissions
FOR EACH ROW EXECUTE FUNCTION trg_fn_audit('admission_id');

CREATE TRIGGER trg_audit_bills
AFTER INSERT OR UPDATE OR DELETE ON bills
FOR EACH ROW EXECUTE FUNCTION trg_fn_audit('bill_id');
