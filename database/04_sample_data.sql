-- =====================================================================
-- 04_sample_data.sql : demo data
-- Dates are relative to CURRENT_DATE so the data always looks recent.
-- Bills are NOT inserted directly: they are produced by the trigger on
-- appointments and by sp_discharge_patient, exactly like in the app.
-- =====================================================================
SET search_path TO hms, public;

INSERT INTO departments (name, floor_no, phone) VALUES
 ('General Medicine', 1, '02226001001'),
 ('Cardiology',       2, '02226001002'),
 ('Orthopaedics',     3, '02226001003'),
 ('Paediatrics',      1, '02226001004'),
 ('Neurology',        4, '02226001005'),
 ('Dermatology',      2, '02226001006');

-- Subclass rows: they also appear when querying the superclass "staff"
INSERT INTO doctors (first_name, last_name, phone, email, hire_date, salary, dept_id,
                     specialization, license_no, consultation_fee) VALUES
 ('Anil',    'Mehta',     '9820011001', 'anil.mehta@cityhospital.in',    '2012-06-01', 180000, 1, 'General Physician',     'MMC-10231', 500),
 ('Sneha',   'Kulkarni',  '9820011002', 'sneha.kulkarni@cityhospital.in','2015-03-15', 250000, 2, 'Cardiologist',          'MMC-11872', 1200),
 ('Rajesh',  'Iyer',      '9820011003', 'rajesh.iyer@cityhospital.in',   '2010-09-20', 240000, 3, 'Orthopaedic Surgeon',   'MMC-09345', 1000),
 ('Priya',   'Deshmukh',  '9820011004', 'priya.deshmukh@cityhospital.in','2018-01-10', 160000, 4, 'Paediatrician',         'MMC-13520', 700),
 ('Farhan',  'Shaikh',    '9820011005', 'farhan.shaikh@cityhospital.in', '2016-07-05', 260000, 5, 'Neurologist',           'MMC-12764', 1500),
 ('Kavita',  'Nair',      '9820011006', 'kavita.nair@cityhospital.in',   '2019-11-25', 150000, 6, 'Dermatologist',         'MMC-14102', 800),
 ('Vikram',  'Joshi',     '9820011007', 'vikram.joshi@cityhospital.in',  '2021-02-01', 140000, 1, 'General Physician',     'MMC-15233', 400),
 ('Meera',   'Pillai',    '9820011008', 'meera.pillai@cityhospital.in',  '2014-08-18', 230000, 2, 'Cardiac Surgeon',       'MMC-11209', 1500);

INSERT INTO nurses (first_name, last_name, phone, email, hire_date, salary, dept_id, shift, ward) VALUES
 ('Asha',    'Patil',     '9820022001', 'asha.patil@cityhospital.in',    '2017-04-12', 45000, 1, 'Morning', 'General Ward A'),
 ('Rohit',   'Sawant',    '9820022002', 'rohit.sawant@cityhospital.in',  '2019-06-30', 42000, 2, 'Night',   'ICCU'),
 ('Neha',    'Gupta',     '9820022003', 'neha.gupta@cityhospital.in',    '2020-01-20', 40000, 3, 'Evening', 'Ortho Ward'),
 ('Sunita',  'Fernandes', '9820022004', 'sunita.f@cityhospital.in',      '2013-10-02', 52000, 4, 'Morning', 'Children Ward'),
 ('Imran',   'Khan',      '9820022005', 'imran.khan@cityhospital.in',    '2022-03-14', 38000, 5, 'Night',   'Neuro ICU');

INSERT INTO patients (first_name, last_name, dob, gender, blood_group, phone, email, address, allergies) VALUES
 ('Rahul',   'Sharma',    '1985-04-12', 'Male',   'B+',  '9930010001', 'rahul.sharma@gmail.com',   ROW('12 MG Road', 'Mumbai', 'Maharashtra', '400001'), '{Penicillin}'),
 ('Pooja',   'Verma',     '1992-08-23', 'Female', 'O+',  '9930010002', 'pooja.verma@gmail.com',    ROW('45 Linking Road', 'Mumbai', 'Maharashtra', '400050'), '{}'),
 ('Amit',    'Patel',     '1978-01-05', 'Male',   'A+',  '9930010003', 'amit.patel@yahoo.com',     ROW('8 SV Road', 'Mumbai', 'Maharashtra', '400058'), '{Sulfa drugs,Peanuts}'),
 ('Sana',    'Qureshi',   '2001-11-30', 'Female', 'AB+', '9930010004', 'sana.q@gmail.com',         ROW('22 Hill Road', 'Mumbai', 'Maharashtra', '400050'), '{}'),
 ('Karan',   'Malhotra',  '1965-06-17', 'Male',   'O-',  '9930010005', NULL,                       ROW('3 Juhu Tara Rd', 'Mumbai', 'Maharashtra', '400049'), '{Aspirin}'),
 ('Anjali',  'Rao',       '2016-02-09', 'Female', 'B-',  '9930010006', 'rao.family@gmail.com',     ROW('17 Powai Lake Rd', 'Mumbai', 'Maharashtra', '400076'), '{}'),
 ('Suresh',  'Yadav',     '1958-12-01', 'Male',   'A-',  '9930010007', NULL,                       ROW('90 Station Rd', 'Thane', 'Maharashtra', '400601'), '{Iodine}'),
 ('Deepa',   'Menon',     '1989-07-14', 'Female', 'O+',  '9930010008', 'deepa.menon@outlook.com',  ROW('5 Carter Road', 'Mumbai', 'Maharashtra', '400050'), '{}'),
 ('Arjun',   'Reddy',     '1995-03-27', 'Male',   'B+',  '9930010009', 'arjun.reddy@gmail.com',    ROW('61 FC Road', 'Pune', 'Maharashtra', '411004'), '{Latex}'),
 ('Fatima',  'Sheikh',    '1972-09-19', 'Female', 'A+',  '9930010010', NULL,                       ROW('14 Mohammed Ali Rd', 'Mumbai', 'Maharashtra', '400003'), '{}'),
 ('Nikhil',  'Bhosale',   '2010-05-05', 'Male',   'O+',  '9930010011', 'bhosale.n@gmail.com',      ROW('29 Gokhale Rd', 'Thane', 'Maharashtra', '400602'), '{Peanuts}'),
 ('Ritu',    'Agarwal',   '1983-10-10', 'Female', 'AB-', '9930010012', 'ritu.agarwal@gmail.com',   ROW('77 Marine Drive', 'Mumbai', 'Maharashtra', '400020'), '{}'),
 ('Manoj',   'Tiwari',    '1969-01-22', 'Male',   'B+',  '9930010013', NULL,                       ROW('11 LBS Marg', 'Mumbai', 'Maharashtra', '400070'), '{Penicillin,Aspirin}'),
 ('Shreya',  'Kapoor',    '1998-12-15', 'Female', 'A+',  '9930010014', 'shreya.k@gmail.com',       ROW('40 Bandstand', 'Mumbai', 'Maharashtra', '400050'), '{}'),
 ('Gopal',   'Krishnan',  '1950-04-03', 'Male',   'O+',  '9930010015', NULL,                       ROW('2 Chembur Colony', 'Mumbai', 'Maharashtra', '400071'), '{}');

INSERT INTO rooms (room_number, room_type, daily_charge, status) VALUES
 ('G-101', 'General',      1500, 'Available'),
 ('G-102', 'General',      1500, 'Available'),
 ('G-103', 'General',      1500, 'Available'),
 ('S-201', 'Semi-Private', 3000, 'Available'),
 ('S-202', 'Semi-Private', 3000, 'Available'),
 ('P-301', 'Private',      6000, 'Available'),
 ('P-302', 'Private',      6000, 'Maintenance'),
 ('I-401', 'ICU',         12000, 'Available'),
 ('I-402', 'ICU',         12000, 'Available'),
 ('P-303', 'Private',      6000, 'Available');

INSERT INTO medicines (name, unit_price, stock_qty, reorder_level) VALUES
 ('Paracetamol 500mg',     2.50, 500, 100),
 ('Amoxicillin 250mg',     6.00, 200,  50),
 ('Atorvastatin 10mg',     8.00, 150,  40),
 ('Metformin 500mg',       3.00, 300,  80),
 ('Amlodipine 5mg',        4.50, 180,  50),
 ('Cetirizine 10mg',       1.80, 250,  60),
 ('Ibuprofen 400mg',       3.20,  15,  60),  -- below reorder level
 ('Pantoprazole 40mg',     5.50, 220,  50),
 ('Clopidogrel 75mg',     12.00,   8,  30),  -- below reorder level
 ('Vitamin D3 60000IU',   30.00,  90,  20);

-- ---------------------------------------------------------------------
-- Appointments: everything starts as Scheduled
-- ---------------------------------------------------------------------
INSERT INTO appointments (patient_id, doctor_id, appointment_time, reason) VALUES
 ( 1, 1, (CURRENT_DATE - 60) + TIME '10:00', 'Fever and body ache'),          -- 1
 ( 2, 6, (CURRENT_DATE - 55) + TIME '11:30', 'Skin rash'),                    -- 2
 ( 3, 2, (CURRENT_DATE - 50) + TIME '09:30', 'Chest pain on exertion'),       -- 3
 ( 5, 2, (CURRENT_DATE - 45) + TIME '12:00', 'High blood pressure follow-up'),-- 4
 ( 6, 4, (CURRENT_DATE - 40) + TIME '10:30', 'Routine vaccination'),          -- 5
 ( 7, 3, (CURRENT_DATE - 35) + TIME '15:00', 'Knee pain'),                    -- 6
 ( 8, 1, (CURRENT_DATE - 30) + TIME '16:00', 'Diabetes check-up'),            -- 7
 ( 9, 5, (CURRENT_DATE - 28) + TIME '11:00', 'Migraine'),                     -- 8
 (10, 7, (CURRENT_DATE - 25) + TIME '09:00', 'Cough and cold'),               -- 9
 (11, 4, (CURRENT_DATE - 20) + TIME '17:00', 'Allergy consultation'),         -- 10
 (12, 8, (CURRENT_DATE - 15) + TIME '13:00', 'Pre-operative assessment'),     -- 11
 (13, 1, (CURRENT_DATE - 12) + TIME '10:00', 'Acidity'),                      -- 12
 (14, 6, (CURRENT_DATE - 10) + TIME '14:30', 'Acne treatment'),               -- 13
 ( 4, 5, (CURRENT_DATE -  7) + TIME '12:30', 'Dizziness'),                    -- 14
 (15, 2, (CURRENT_DATE -  5) + TIME '10:00', 'Palpitations'),                 -- 15
 ( 1, 7, (CURRENT_DATE -  3) + TIME '18:00', 'Follow-up'),                    -- 16
 ( 2, 1, (CURRENT_DATE +  1) + TIME '10:00', 'Annual health check'),          -- 17
 ( 3, 2, (CURRENT_DATE +  2) + TIME '11:00', 'ECG review'),                   -- 18
 ( 9, 5, (CURRENT_DATE +  3) + TIME '12:00', 'Migraine follow-up'),           -- 19
 (12, 3, (CURRENT_DATE +  4) + TIME '15:30', 'Back pain'),                    -- 20
 ( 6, 4, (CURRENT_DATE +  6) + TIME '09:30', 'Growth check'),                 -- 21
 (14, 6, (CURRENT_DATE +  8) + TIME '16:30', 'Acne follow-up');               -- 22

-- Prescriptions (each insert fires the stock trigger)
INSERT INTO prescriptions (appointment_id, medicine_id, dosage, quantity, duration_days) VALUES
 ( 1, 1, '1 tablet thrice daily',  15, 5),
 ( 2, 6, '1 tablet at night',      10, 10),
 ( 3, 3, '1 tablet at night',      30, 30),
 ( 3, 9, '1 tablet daily',          5, 5),
 ( 4, 5, '1 tablet daily',         30, 30),
 ( 6, 7, '1 tablet twice daily',   10, 5),
 ( 7, 4, '1 tablet twice daily',   60, 30),
 ( 8, 1, '1 tablet when needed',   10, 10),
 ( 9, 2, '1 capsule thrice daily', 15, 5),
 (10, 6, '1 tablet daily',          7, 7),
 (12, 8, '1 tablet before food',   14, 14),
 (13, 6, '1 tablet at night',      10, 10),
 (14, 10,'1 sachet weekly',         4, 28),
 (15, 3, '1 tablet at night',      30, 30),
 (16, 1, '1 tablet thrice daily',   9, 3);

-- Completing appointments fires trg_appointment_bill -> bills are created
UPDATE appointments SET status = 'Completed' WHERE appointment_id IN (1,2,3,4,5,6,7,8,9,10,12,13,14,15,16);
UPDATE appointments SET status = 'Cancelled' WHERE appointment_id = 11;

-- ---------------------------------------------------------------------
-- Admissions through the stored procedures
-- ---------------------------------------------------------------------
CALL sp_admit_patient(3,  8, 2, 'Unstable angina',             CURRENT_DATE - 48);  -- adm 1
CALL sp_discharge_patient(1, CURRENT_DATE - 43);
CALL sp_admit_patient(7,  4, 3, 'Total knee replacement',      CURRENT_DATE - 33);  -- adm 2
CALL sp_discharge_patient(2, CURRENT_DATE - 26);
CALL sp_admit_patient(9,  1, 5, 'Severe migraine, observation', CURRENT_DATE - 27); -- adm 3
CALL sp_discharge_patient(3, CURRENT_DATE - 25);
CALL sp_admit_patient(15, 9, 2, 'Atrial fibrillation',         CURRENT_DATE - 4);   -- adm 4 (active)
CALL sp_admit_patient(5,  6, 8, 'Coronary bypass surgery',     CURRENT_DATE - 2);   -- adm 5 (active)
CALL sp_admit_patient(13, 2, 1, 'Dengue fever',                CURRENT_DATE - 1);   -- adm 6 (active)

-- Some bills have been paid
UPDATE bills SET payment_status = 'Paid', paid_on = bill_date
 WHERE bill_id IN (SELECT bill_id FROM bills ORDER BY bill_id LIMIT 12);

-- ---------------------------------------------------------------------
-- Medical records: JSONB lab reports and an XML discharge summary
-- ---------------------------------------------------------------------
INSERT INTO medical_records (patient_id, doctor_id, record_type, recorded_at, details, summary_xml) VALUES
 (3, 2, 'Lab Report', (CURRENT_DATE - 50) + TIME '11:00',
  '{"test": "Lipid Profile", "results": {"total_cholesterol": 245, "ldl": 165, "hdl": 38, "triglycerides": 210}, "unit": "mg/dL", "flag": "High"}', NULL),
 (3, 2, 'Lab Report', (CURRENT_DATE - 48) + TIME '09:00',
  '{"test": "Troponin I", "results": {"troponin_i": 0.08}, "unit": "ng/mL", "flag": "Borderline"}', NULL),
 (8, 1, 'Lab Report', (CURRENT_DATE - 30) + TIME '17:00',
  '{"test": "HbA1c", "results": {"hba1c": 7.4}, "unit": "%", "flag": "High"}', NULL),
 (1, 1, 'Lab Report', (CURRENT_DATE - 60) + TIME '12:00',
  '{"test": "Complete Blood Count", "results": {"hemoglobin": 13.8, "wbc": 11200, "platelets": 180000}, "flag": "Normal"}', NULL),
 (13, 1, 'Lab Report', (CURRENT_DATE - 1) + TIME '10:00',
  '{"test": "Dengue NS1 Antigen", "results": {"ns1": "Positive", "platelets": 85000}, "flag": "Critical"}', NULL),
 (5, 8, 'Vitals', (CURRENT_DATE - 2) + TIME '08:00',
  '{"bp": {"systolic": 160, "diastolic": 100}, "pulse": 92, "spo2": 95, "temperature_c": 37.1}', NULL),
 (7, 3, 'Discharge Summary', (CURRENT_DATE - 26) + TIME '12:00',
  '{"procedure": "Total knee replacement (right)", "follow_up_days": 14}',
  '<discharge_summary>
     <diagnosis>Osteoarthritis right knee</diagnosis>
     <procedure>Total knee replacement</procedure>
     <medications>
       <medicine dose="400mg" frequency="BD">Ibuprofen</medicine>
       <medicine dose="40mg"  frequency="OD">Pantoprazole</medicine>
     </medications>
     <follow_up days="14">Orthopaedics OPD</follow_up>
   </discharge_summary>'),
 (3, 2, 'Discharge Summary', (CURRENT_DATE - 43) + TIME '12:00',
  '{"procedure": "Medical management", "follow_up_days": 7}',
  '<discharge_summary>
     <diagnosis>Unstable angina</diagnosis>
     <procedure>Medical management, angiography advised</procedure>
     <medications>
       <medicine dose="10mg" frequency="HS">Atorvastatin</medicine>
       <medicine dose="75mg" frequency="OD">Clopidogrel</medicine>
     </medications>
     <follow_up days="7">Cardiology OPD</follow_up>
   </discharge_summary>');

REFRESH MATERIALIZED VIEW mv_monthly_revenue;
