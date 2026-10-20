"""Demo data. Dates are relative to today so the data always looks recent.
Bills are NOT inserted directly: they come from completing appointments
and discharging patients through services.py, exactly like in the app.

The first part is a fixed, hand-written data set (the demo cases in the
README rely on it). On top of that, about six months of extra visit
history is generated with a fixed random seed, so every run of
init_db.py produces the same data.
"""
import random
from datetime import date, datetime, time, timedelta
from xml.sax.saxutils import escape

from pymongo.errors import DuplicateKeyError

import services as hms
from db import HMSError, get_db, next_id, to_datetime

DEPARTMENTS = [
    ("General Medicine", 1, "02226001001"),
    ("Cardiology",       2, "02226001002"),
    ("Orthopaedics",     3, "02226001003"),
    ("Paediatrics",      1, "02226001004"),
    ("Neurology",        4, "02226001005"),
    ("Dermatology",      2, "02226001006"),
    ("ENT",              3, "02226001007"),
    ("Gynaecology",      4, "02226001008"),
    ("Ophthalmology",    5, "02226001009"),
    ("Psychiatry",       5, "02226001010"),
]

# first, last, phone, email, hire_date, salary, dept_id, specialization, license_no, fee
# staff ids follow this order: doctors are 1-14, nurses 15-24
DOCTORS = [
    ("Anil",    "Mehta",    "9820011001", "anil.mehta@cityhospital.in",      "2012-06-01", 180000, 1,  "General Physician",   "MMC-10231", 500),
    ("Sneha",   "Kulkarni", "9820011002", "sneha.kulkarni@cityhospital.in",  "2015-03-15", 250000, 2,  "Cardiologist",        "MMC-11872", 1200),
    ("Rajesh",  "Iyer",     "9820011003", "rajesh.iyer@cityhospital.in",     "2010-09-20", 240000, 3,  "Orthopaedic Surgeon", "MMC-09345", 1000),
    ("Priya",   "Deshmukh", "9820011004", "priya.deshmukh@cityhospital.in",  "2018-01-10", 160000, 4,  "Paediatrician",       "MMC-13520", 700),
    ("Farhan",  "Shaikh",   "9820011005", "farhan.shaikh@cityhospital.in",   "2016-07-05", 260000, 5,  "Neurologist",         "MMC-12764", 1500),
    ("Kavita",  "Nair",     "9820011006", "kavita.nair@cityhospital.in",     "2019-11-25", 150000, 6,  "Dermatologist",       "MMC-14102", 800),
    ("Vikram",  "Joshi",    "9820011007", "vikram.joshi@cityhospital.in",    "2021-02-01", 140000, 1,  "General Physician",   "MMC-15233", 400),
    ("Meera",   "Pillai",   "9820011008", "meera.pillai@cityhospital.in",    "2014-08-18", 230000, 2,  "Cardiac Surgeon",     "MMC-11209", 1500),
    ("Rohan",   "Desai",    "9820011009", "rohan.desai@cityhospital.in",     "2017-05-22", 170000, 7,  "ENT Specialist",      "MMC-13011", 800),
    ("Ananya",  "Bose",     "9820011010", "ananya.bose@cityhospital.in",     "2013-12-02", 220000, 8,  "Gynaecologist",       "MMC-10988", 1000),
    ("Sameer",  "Khanna",   "9820011011", "sameer.khanna@cityhospital.in",   "2020-08-17", 155000, 9,  "Ophthalmologist",     "MMC-14876", 700),
    ("Lakshmi", "Iyengar",  "9820011012", "lakshmi.iyengar@cityhospital.in", "2011-04-11", 210000, 10, "Psychiatrist",        "MMC-09977", 1500),
    ("Harish",  "Menon",    "9820011013", "harish.menon@cityhospital.in",    "2019-03-04", 200000, 3,  "Orthopaedic Surgeon", "MMC-14390", 1100),
    ("Nisha",   "Chopra",   "9820011014", "nisha.chopra@cityhospital.in",    "2022-06-20", 135000, 4,  "Paediatrician",       "MMC-15612", 600),
]

# first, last, phone, email, hire_date, salary, dept_id, shift, ward
NURSES = [
    ("Asha",    "Patil",     "9820022001", "asha.patil@cityhospital.in",     "2017-04-12", 45000, 1, "Morning", "General Ward A"),
    ("Rohit",   "Sawant",    "9820022002", "rohit.sawant@cityhospital.in",   "2019-06-30", 42000, 2, "Night",   "ICCU"),
    ("Neha",    "Gupta",     "9820022003", "neha.gupta@cityhospital.in",     "2020-01-20", 40000, 3, "Evening", "Ortho Ward"),
    ("Sunita",  "Fernandes", "9820022004", "sunita.f@cityhospital.in",       "2013-10-02", 52000, 4, "Morning", "Children Ward"),
    ("Imran",   "Khan",      "9820022005", "imran.khan@cityhospital.in",     "2022-03-14", 38000, 5, "Night",   "Neuro ICU"),
    ("Pallavi", "Jadhav",    "9820022006", "pallavi.jadhav@cityhospital.in", "2018-09-03", 43000, 7, "Evening", "ENT Ward"),
    ("Meenal",  "Shinde",    "9820022007", "meenal.shinde@cityhospital.in",  "2016-02-15", 47000, 8, "Morning", "Maternity Ward"),
    ("George",  "D'Souza",   "9820022008", "george.dsouza@cityhospital.in",  "2021-07-26", 39000, 2, "Evening", "Cardiac Ward"),
    ("Kiran",   "More",      "9820022009", "kiran.more@cityhospital.in",     "2023-01-09", 36000, 1, "Night",   "General Ward B"),
    ("Farida",  "Ansari",    "9820022010", "farida.ansari@cityhospital.in",  "2019-11-11", 41000, 9, "Morning", "Eye Ward"),
]

# first, last, dob, gender, blood, phone, email, (street, city, pincode), allergies
PATIENTS = [
    ("Rahul",    "Sharma",     "1985-04-12", "Male",   "B+",  "9930010001", "rahul.sharma@gmail.com",   ("12 MG Road", "Mumbai", "400001"),          ["Penicillin"]),
    ("Pooja",    "Verma",      "1992-08-23", "Female", "O+",  "9930010002", "pooja.verma@gmail.com",    ("45 Linking Road", "Mumbai", "400050"),     []),
    ("Amit",     "Patel",      "1978-01-05", "Male",   "A+",  "9930010003", "amit.patel@yahoo.com",     ("8 SV Road", "Mumbai", "400058"),           ["Sulfa drugs", "Peanuts"]),
    ("Sana",     "Qureshi",    "2001-11-30", "Female", "AB+", "9930010004", "sana.q@gmail.com",         ("22 Hill Road", "Mumbai", "400050"),        []),
    ("Karan",    "Malhotra",   "1965-06-17", "Male",   "O-",  "9930010005", None,                       ("3 Juhu Tara Rd", "Mumbai", "400049"),      ["Aspirin"]),
    ("Anjali",   "Rao",        "2016-02-09", "Female", "B-",  "9930010006", "rao.family@gmail.com",     ("17 Powai Lake Rd", "Mumbai", "400076"),    []),
    ("Suresh",   "Yadav",      "1958-12-01", "Male",   "A-",  "9930010007", None,                       ("90 Station Rd", "Thane", "400601"),        ["Iodine"]),
    ("Deepa",    "Menon",      "1989-07-14", "Female", "O+",  "9930010008", "deepa.menon@outlook.com",  ("5 Carter Road", "Mumbai", "400050"),       []),
    ("Arjun",    "Reddy",      "1995-03-27", "Male",   "B+",  "9930010009", "arjun.reddy@gmail.com",    ("61 FC Road", "Pune", "411004"),            ["Latex"]),
    ("Fatima",   "Sheikh",     "1972-09-19", "Female", "A+",  "9930010010", None,                       ("14 Mohammed Ali Rd", "Mumbai", "400003"),  []),
    ("Nikhil",   "Bhosale",    "2010-05-05", "Male",   "O+",  "9930010011", "bhosale.n@gmail.com",      ("29 Gokhale Rd", "Thane", "400602"),        ["Peanuts"]),
    ("Ritu",     "Agarwal",    "1983-10-10", "Female", "AB-", "9930010012", "ritu.agarwal@gmail.com",   ("77 Marine Drive", "Mumbai", "400020"),     []),
    ("Manoj",    "Tiwari",     "1969-01-22", "Male",   "B+",  "9930010013", None,                       ("11 LBS Marg", "Mumbai", "400070"),         ["Penicillin", "Aspirin"]),
    ("Shreya",   "Kapoor",     "1998-12-15", "Female", "A+",  "9930010014", "shreya.k@gmail.com",       ("40 Bandstand", "Mumbai", "400050"),        []),
    ("Gopal",    "Krishnan",   "1950-04-03", "Male",   "O+",  "9930010015", None,                       ("2 Chembur Colony", "Mumbai", "400071"),    []),
    ("Aditya",   "Kulkarni",   "1990-02-18", "Male",   "A+",  "9930010016", "aditya.k@gmail.com",       ("33 Prabhat Rd", "Pune", "411004"),         []),
    ("Priyanka", "Joshi",      "1987-06-25", "Female", "B+",  "9930010017", "priyanka.joshi@gmail.com", ("9 Naupada", "Thane", "400602"),            ["Sulfa drugs"]),
    ("Vivek",    "Pandey",     "1976-11-08", "Male",   "O+",  "9930010018", None,                       ("51 Kurla West", "Mumbai", "400070"),       []),
    ("Lata",     "Gaikwad",    "1961-03-14", "Female", "A-",  "9930010019", None,                       ("6 Dadar East", "Mumbai", "400014"),        ["Penicillin"]),
    ("Rakesh",   "Singh",      "1955-09-30", "Male",   "B-",  "9930010020", "rakesh.singh@yahoo.com",   ("19 Vashi Sector 9", "Navi Mumbai", "400703"), []),
    ("Meghna",   "Shah",       "1994-01-21", "Female", "O+",  "9930010021", "meghna.shah@gmail.com",    ("70 Ghatkopar East", "Mumbai", "400077"),   []),
    ("Sneha",    "Pawar",      "1996-05-02", "Female", "AB+", "9930010022", "sneha.pawar@gmail.com",    ("4 Kothrud", "Pune", "411038"),             []),
    ("Imtiaz",   "Ali",        "1980-12-12", "Male",   "A+",  "9930010023", None,                       ("88 Bhendi Bazaar", "Mumbai", "400003"),    ["Aspirin"]),
    ("Kavya",    "Nambiar",    "2012-08-08", "Female", "B+",  "9930010024", "nambiar.home@gmail.com",   ("15 Chembur Naka", "Mumbai", "400071"),     ["Peanuts", "Eggs"]),
    ("Prakash",  "Jain",       "1948-07-19", "Male",   "O-",  "9930010025", None,                       ("2 Girgaon", "Mumbai", "400004"),           []),
    ("Ayesha",   "Khan",       "1999-04-04", "Female", "A+",  "9930010026", "ayesha.khan@gmail.com",    ("27 Mira Road", "Thane", "401107"),         []),
    ("Neelam",   "Dubey",      "1991-10-27", "Female", "B+",  "9930010027", "neelam.d@gmail.com",       ("63 Borivali West", "Mumbai", "400092"),    []),
    ("Siddharth", "Rane",      "1984-02-29", "Male",   "AB+", "9930010028", "sid.rane@outlook.com",     ("10 Andheri East", "Mumbai", "400069"),     ["Latex"]),
    ("Tanvi",    "Mhatre",     "2005-12-03", "Female", "O+",  "9930010029", "tanvi.m@gmail.com",        ("41 Panvel", "Navi Mumbai", "410206"),      []),
    ("Bhavesh",  "Thakkar",    "1967-08-16", "Male",   "A+",  "9930010030", None,                       ("8 Mulund West", "Mumbai", "400080"),       []),
    ("Rekha",    "Nair",       "1959-05-23", "Female", "B+",  "9930010031", None,                       ("55 Sion", "Mumbai", "400022"),             ["Iodine"]),
    ("Omkar",    "Sawant",     "2000-09-09", "Male",   "O+",  "9930010032", "omkar.sawant@gmail.com",   ("13 Kalyan West", "Thane", "421301"),       []),
    ("Jyoti",    "Mishra",     "1974-03-06", "Female", "A-",  "9930010033", "jyoti.mishra@gmail.com",   ("29 Malad West", "Mumbai", "400064"),       []),
    ("Farhan",   "Merchant",   "1988-11-17", "Male",   "B+",  "9930010034", "farhan.m@gmail.com",       ("3 Colaba Causeway", "Mumbai", "400005"),   ["Penicillin"]),
    ("Aarav",    "Deshpande",  "2023-01-15", "Male",   "O+",  "9930010035", "deshpande.fam@gmail.com",  ("18 Aundh", "Pune", "411007"),              []),
    ("Smita",    "Patkar",     "1979-07-07", "Female", "AB-", "9930010036", None,                       ("72 Vile Parle East", "Mumbai", "400057"),  []),
    ("Yusuf",    "Pathan",     "1993-06-13", "Male",   "A+",  "9930010037", "yusuf.p@gmail.com",        ("6 Bandra West", "Mumbai", "400050"),       []),
    ("Geeta",    "Iyer",       "1952-10-01", "Female", "O+",  "9930010038", None,                       ("24 Matunga", "Mumbai", "400019"),          ["Sulfa drugs"]),
    ("Harsh",    "Vora",       "2014-04-22", "Male",   "B+",  "9930010039", "vora.family@gmail.com",    ("47 Kandivali East", "Mumbai", "400101"),   []),
    ("Anita",    "Chavan",     "1986-12-28", "Female", "B-",  "9930010040", "anita.chavan@gmail.com",   ("31 Dombivli East", "Thane", "421201"),     []),
]

ROOMS = [
    ("G-101", "General", 1500, "Available"), ("G-102", "General", 1500, "Available"),
    ("G-103", "General", 1500, "Available"), ("S-201", "Semi-Private", 3000, "Available"),
    ("S-202", "Semi-Private", 3000, "Available"), ("P-301", "Private", 6000, "Available"),
    ("P-302", "Private", 6000, "Maintenance"), ("I-401", "ICU", 12000, "Available"),
    ("I-402", "ICU", 12000, "Available"), ("P-303", "Private", 6000, "Available"),
    ("G-104", "General", 1500, "Available"), ("G-105", "General", 1500, "Available"),
    ("S-203", "Semi-Private", 3000, "Available"), ("P-304", "Private", 6000, "Available"),
    ("I-403", "ICU", 12000, "Available"), ("P-305", "Private", 6500, "Available"),
    ("G-106", "General", 1500, "Maintenance"),
]

# name, unit price, stock before any prescriptions, reorder level
MEDICINES = [
    ("Paracetamol 500mg", 2.50, 2000, 100), ("Amoxicillin 250mg", 6.00, 800, 50),
    ("Atorvastatin 10mg", 8.00, 900, 40), ("Metformin 500mg", 3.00, 1200, 80),
    ("Amlodipine 5mg", 4.50, 900, 50), ("Cetirizine 10mg", 1.80, 1200, 60),
    ("Ibuprofen 400mg", 3.20, 15, 60),       # below reorder level (demo)
    ("Pantoprazole 40mg", 5.50, 900, 50),
    ("Clopidogrel 75mg", 12.00, 8, 30),      # below reorder level (demo)
    ("Vitamin D3 60000IU", 30.00, 300, 20),
    ("Azithromycin 500mg", 22.00, 400, 30), ("Omeprazole 20mg", 3.50, 800, 60),
    ("Losartan 50mg", 5.00, 700, 50), ("Salbutamol Inhaler", 150.00, 60, 10),
    ("Insulin Glargine", 650.00, 40, 10), ("Levothyroxine 50mcg", 1.50, 900, 80),
    ("Montelukast 10mg", 9.00, 500, 40), ("Diclofenac Gel", 85.00, 80, 15),
    ("Ondansetron 4mg", 4.00, 500, 40), ("Ciprofloxacin 500mg", 7.50, 500, 40),
    ("ORS Sachet", 20.00, 25, 50),           # below reorder level (demo)
    ("Eye Drops Moxifloxacin", 95.00, 70, 15),
]

# patient, doctor, days from today, time, reason  (ids 1..22 in this order)
APPOINTMENTS = [
    (1, 1, -60, "10:00", "Fever and body ache"), (2, 6, -55, "11:30", "Skin rash"),
    (3, 2, -50, "09:30", "Chest pain on exertion"), (5, 2, -45, "12:00", "High blood pressure follow-up"),
    (6, 4, -40, "10:30", "Routine vaccination"), (7, 3, -35, "15:00", "Knee pain"),
    (8, 1, -30, "16:00", "Diabetes check-up"), (9, 5, -28, "11:00", "Migraine"),
    (10, 7, -25, "09:00", "Cough and cold"), (11, 4, -20, "17:00", "Allergy consultation"),
    (12, 8, -15, "13:00", "Pre-operative assessment"), (13, 1, -12, "10:00", "Acidity"),
    (14, 6, -10, "14:30", "Acne treatment"), (4, 5, -7, "12:30", "Dizziness"),
    (15, 2, -5, "10:00", "Palpitations"), (1, 7, -3, "18:00", "Follow-up"),
    (2, 1, 1, "10:00", "Annual health check"), (3, 2, 2, "11:00", "ECG review"),
    (9, 5, 3, "12:00", "Migraine follow-up"), (12, 3, 4, "15:30", "Back pain"),
    (6, 4, 6, "09:30", "Growth check"), (14, 6, 8, "16:30", "Acne follow-up"),
]

# appointment, medicine, dosage, quantity, days
PRESCRIPTIONS = [
    (1, 1, "1 tablet thrice daily", 15, 5), (2, 6, "1 tablet at night", 10, 10),
    (3, 3, "1 tablet at night", 30, 30), (3, 9, "1 tablet daily", 5, 5),
    (4, 5, "1 tablet daily", 30, 30), (6, 7, "1 tablet twice daily", 10, 5),
    (7, 4, "1 tablet twice daily", 60, 30), (8, 1, "1 tablet when needed", 10, 10),
    (9, 2, "1 capsule thrice daily", 15, 5), (10, 6, "1 tablet daily", 7, 7),
    (12, 8, "1 tablet before food", 14, 14), (13, 6, "1 tablet at night", 10, 10),
    (14, 10, "1 sachet weekly", 4, 28), (15, 3, "1 tablet at night", 30, 30),
    (16, 1, "1 tablet thrice daily", 9, 3),
]

# patient, room, doctor, diagnosis, admitted (days ago), discharged (days ago or None)
# processed oldest first, so stays in the same room never overlap
ADMISSIONS = [
    (18, 11, 9,  "Tonsillectomy",                 150, 147),
    (5,  8,  2,  "Hypertensive crisis",           140, 137),
    (22, 16, 10, "Normal delivery",               120, 117),
    (25, 13, 13, "Hip fracture fixation",         110, 102),
    (30, 15, 2,  "Acute myocardial infarction",    95,  88),
    (33, 12, 1,  "Typhoid fever",                  70,  64),
    (38, 4,  7,  "Viral pneumonia",                60,  55),
    (3,  8,  2,  "Unstable angina",                48,  43),
    (20, 14, 11, "Cataract surgery",               40,  39),
    (7,  4,  3,  "Total knee replacement",         33,  26),
    (9,  1,  5,  "Severe migraine, observation",   27,  25),
    (12, 6,  8,  "Mitral valve repair",            14,   6),
    (15, 9,  2,  "Atrial fibrillation",             4, None),
    (27, 16, 10, "Caesarean section",               3, None),
    (5,  6,  8,  "Coronary bypass surgery",         2, None),
    (35, 11, 14, "Bronchiolitis",                   2, None),
    (13, 2,  1,  "Dengue fever",                    1, None),
]

KNEE_SUMMARY = """<discharge_summary>
  <diagnosis>Osteoarthritis right knee</diagnosis>
  <procedure>Total knee replacement</procedure>
  <medications>
    <medicine dose="400mg" frequency="BD">Ibuprofen</medicine>
    <medicine dose="40mg" frequency="OD">Pantoprazole</medicine>
  </medications>
  <follow_up days="14">Orthopaedics OPD</follow_up>
</discharge_summary>"""

ANGINA_SUMMARY = """<discharge_summary>
  <diagnosis>Unstable angina</diagnosis>
  <procedure>Medical management, angiography advised</procedure>
  <medications>
    <medicine dose="10mg" frequency="HS">Atorvastatin</medicine>
    <medicine dose="75mg" frequency="OD">Clopidogrel</medicine>
  </medications>
  <follow_up days="7">Cardiology OPD</follow_up>
</discharge_summary>"""

# patient, doctor, type, days ago, time, details, xml
RECORDS = [
    (3, 2, "Lab Report", 50, "11:00", {"test": "Lipid Profile", "results": {"total_cholesterol": 245, "ldl": 165, "hdl": 38, "triglycerides": 210}, "unit": "mg/dL", "flag": "High"}, None),
    (3, 2, "Lab Report", 48, "09:00", {"test": "Troponin I", "results": {"troponin_i": 0.08}, "unit": "ng/mL", "flag": "Borderline"}, None),
    (8, 1, "Lab Report", 30, "17:00", {"test": "HbA1c", "results": {"hba1c": 7.4}, "unit": "%", "flag": "High"}, None),
    (1, 1, "Lab Report", 60, "12:00", {"test": "Complete Blood Count", "results": {"hemoglobin": 13.8, "wbc": 11200, "platelets": 180000}, "flag": "Normal"}, None),
    (13, 1, "Lab Report", 1, "10:00", {"test": "Dengue NS1 Antigen", "results": {"ns1": "Positive", "platelets": 85000}, "flag": "Critical"}, None),
    (5, 8, "Vitals", 2, "08:00", {"bp": {"systolic": 160, "diastolic": 100}, "pulse": 92, "spo2": 95, "temperature_c": 37.1}, None),
    (7, 3, "Discharge Summary", 26, "12:00", {"procedure": "Total knee replacement (right)", "follow_up_days": 14}, KNEE_SUMMARY),
    (3, 2, "Discharge Summary", 43, "12:00", {"procedure": "Medical management", "follow_up_days": 7}, ANGINA_SUMMARY),
]

# ---------------------------------------------------------------------
# Building blocks for the generated visit history
# ---------------------------------------------------------------------
# specialization -> (visit reasons, medicine ids, lab tests ordered)
SPECIALTIES = {
    "General Physician":   (["Fever", "Cough and cold", "Body ache", "Acidity", "Routine check-up",
                             "Diabetes follow-up", "Headache", "Loose motions"], [1, 2, 4, 8, 12, 15, 19, 21],
                            ["Complete Blood Count", "Blood Sugar", "HbA1c", "Liver Function", "Kidney Function"]),
    "Cardiologist":        (["Chest pain", "Palpitations", "BP follow-up", "Breathlessness"], [3, 5, 13],
                            ["Lipid Profile", "ECG"]),
    "Cardiac Surgeon":     (["Post-operative review", "Pre-operative assessment"], [3, 5, 13], ["Lipid Profile", "ECG"]),
    "Orthopaedic Surgeon": (["Knee pain", "Back pain", "Shoulder pain", "Fracture follow-up"], [1, 10, 18],
                            ["Vitamin D"]),
    "Paediatrician":       (["Vaccination", "Fever", "Growth check", "Cough", "Stomach ache"], [1, 6, 17, 21],
                            ["Complete Blood Count"]),
    "Neurologist":         (["Migraine", "Dizziness", "Numbness in hands", "Seizure follow-up"], [1, 10, 19],
                            ["Vitamin D", "Complete Blood Count"]),
    "Dermatologist":       (["Acne", "Skin rash", "Hair fall", "Eczema"], [6, 11], ["Thyroid Profile"]),
    "ENT Specialist":      (["Ear pain", "Sore throat", "Sinusitis", "Hearing check"], [11, 6, 17], ["Complete Blood Count"]),
    "Gynaecologist":       (["Antenatal check-up", "Irregular periods", "PCOS follow-up"], [10, 16, 19],
                            ["Thyroid Profile", "Blood Sugar"]),
    "Ophthalmologist":     (["Blurred vision", "Eye redness", "Cataract review", "Spectacle check"], [6, 22],
                            ["Blood Sugar"]),
    "Psychiatrist":        (["Anxiety", "Insomnia", "Depression follow-up", "Stress counselling"], [], []),
}

DOSAGES = ["1 tablet once daily", "1 tablet twice daily", "1 tablet thrice daily", "1 tablet at night",
           "1 tablet when needed"]
FLAGS = ["Normal"] * 6 + ["Borderline", "Borderline", "High", "High", "Critical"]

LAB_TESTS = {
    "Complete Blood Count": lambda r: ({"hemoglobin": round(r.uniform(9, 16), 1), "wbc": r.randrange(4000, 15000, 100),
                                        "platelets": r.randrange(90000, 400000, 1000)}, None),
    "Blood Sugar":          lambda r: ({"fasting": r.randint(75, 190), "pp": r.randint(100, 290)}, "mg/dL"),
    "HbA1c":                lambda r: ({"hba1c": round(r.uniform(5, 10), 1)}, "%"),
    "Lipid Profile":        lambda r: ({"total_cholesterol": r.randint(150, 290), "ldl": r.randint(70, 200),
                                        "hdl": r.randint(30, 70), "triglycerides": r.randint(90, 300)}, "mg/dL"),
    "Liver Function":       lambda r: ({"sgot": r.randint(15, 120), "sgpt": r.randint(10, 140),
                                        "bilirubin": round(r.uniform(0.3, 2.5), 1)}, None),
    "Kidney Function":      lambda r: ({"creatinine": round(r.uniform(0.6, 2.4), 1), "urea": r.randint(15, 70)}, "mg/dL"),
    "Thyroid Profile":      lambda r: ({"tsh": round(r.uniform(0.4, 9), 2), "t3": round(r.uniform(0.8, 2), 2),
                                        "t4": round(r.uniform(5, 12), 1)}, None),
    "Vitamin D":            lambda r: ({"vitamin_d": r.randint(8, 60)}, "ng/mL"),
    "ECG":                  lambda r: ({"rhythm": r.choice(["Sinus", "Sinus", "Sinus tachycardia", "AF"]),
                                        "rate": r.randint(55, 125)}, "bpm"),
}


def days_ago(n, at="00:00"):
    return datetime.combine(date.today() - timedelta(days=n), time.fromisoformat(at))


def discharge_xml(diagnosis, doctor_dept, follow_up):
    return (f"<discharge_summary>\n  <diagnosis>{escape(diagnosis)}</diagnosis>\n"
            f"  <condition_at_discharge>Stable</condition_at_discharge>\n"
            f"  <follow_up days=\"{follow_up}\">{escape(doctor_dept)} OPD</follow_up>\n</discharge_summary>")


def generate_history(rng, doctors, registered_days_ago):
    """About 150 extra visits over the last six months plus a few booked
    for today and the next two weeks: prescriptions, completions,
    cancellations and lab reports, all through services.py."""
    db = get_db()
    med_prices = {m["medicine_id"]: m["unit_price"] for m in db.medicines.find()}
    patient_ids = list(registered_days_ago)

    def book(patient, doctor, when):
        reasons = SPECIALTIES[doctor["specialization"]][0]
        try:
            return hms.book_appointment(patient, doctor["staff_id"], when, rng.choice(reasons))
        except (HMSError, DuplicateKeyError):   # slot already taken
            return None

    def random_slot():
        return f"{rng.randint(9, 19):02d}:{rng.choice(['00', '15', '30', '45'])}"

    # past visits
    for _ in range(150):
        patient = rng.choice(patient_ids)
        doctor = rng.choice(doctors)
        ago = rng.randint(1, min(180, registered_days_ago[patient] - 1))
        appt = book(patient, doctor, days_ago(ago, random_slot()))
        if appt is None:
            continue
        if rng.random() < 0.1:
            hms.set_appointment_status(appt, "Cancelled")
            continue
        _, meds, tests = SPECIALTIES[doctor["specialization"]]
        for med in rng.sample(meds, k=min(len(meds), rng.choice([0, 1, 1, 2]))):
            qty = rng.randint(1, 2) if med_prices[med] >= 50 else rng.choice([5, 7, 10, 14, 15, 20, 30])
            try:
                hms.prescribe(appt, med, rng.choice(DOSAGES), qty, rng.choice([3, 5, 7, 10, 14, 30]))
            except HMSError:                    # out of stock: skip it
                pass
        hms.set_appointment_status(appt, "Completed")
        if tests and rng.random() < 0.45:
            test = rng.choice(tests)
            results, unit = LAB_TESTS[test](rng)
            details = {"test": test, "results": results, "flag": rng.choice(FLAGS)}
            if unit:
                details["unit"] = unit
            hms.add_medical_record(patient, "Lab Report", details, doctor_id=doctor["staff_id"],
                                   recorded_at=days_ago(ago, "18:30"))

    # booked for today and the coming two weeks
    for offset in [0] * 5 + [rng.randint(1, 14) for _ in range(25)]:
        book(rng.choice(patient_ids), rng.choice(doctors), days_ago(-offset, random_slot()))


def load():
    db = get_db()
    rng = random.Random(2026)

    db.departments.insert_many([{"dept_id": next_id("departments"), "name": n, "floor_no": f, "phone": ph}
                                for n, f, ph in DEPARTMENTS])

    # doctors and nurses share the staff collection and its id sequence
    staff = []
    for first, last, phone, email, hired, salary, dept, spec, lic, fee in DOCTORS:
        staff.append({"staff_id": next_id("staff"), "role": "Doctor", "first_name": first, "last_name": last,
                      "phone": phone, "email": email, "hire_date": to_datetime(hired), "salary": salary,
                      "dept_id": dept, "specialization": spec, "license_no": lic, "consultation_fee": fee})
    for first, last, phone, email, hired, salary, dept, shift, ward in NURSES:
        staff.append({"staff_id": next_id("staff"), "role": "Nurse", "first_name": first, "last_name": last,
                      "phone": phone, "email": email, "hire_date": to_datetime(hired), "salary": salary,
                      "dept_id": dept, "shift": shift, "ward": ward})
    db.staff.insert_many(staff)

    registered = {}
    for i, (first, last, dob, gender, blood, phone, email, (street, city, pin), allergies) in enumerate(PATIENTS):
        ago = 220 - i * 4
        patient_id = hms.create_patient(
            {"first_name": first, "last_name": last, "dob": dob, "gender": gender, "blood_group": blood,
             "phone": phone, "email": email, "street": street, "city": city, "state": "Maharashtra",
             "pincode": pin, "allergies": allergies},
            registered_on=days_ago(ago, "09:00"))
        registered[patient_id] = ago

    db.rooms.insert_many([{"room_id": next_id("rooms"), "room_number": n, "room_type": t,
                           "daily_charge": c, "status": s} for n, t, c, s in ROOMS])
    db.medicines.insert_many([{"medicine_id": next_id("medicines"), "name": n, "unit_price": p,
                               "stock_qty": q, "reorder_level": r} for n, p, q, r in MEDICINES])

    # fixed appointments first, so their ids are 1..22
    for patient, doctor, offset, at, reason in APPOINTMENTS:
        hms.book_appointment(patient, doctor, days_ago(-offset, at), reason)
    for appt, med, dosage, qty, days in PRESCRIPTIONS:
        hms.prescribe(appt, med, dosage, qty, days)          # reduces stock
    for appt in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16):
        hms.set_appointment_status(appt, "Completed")       # creates the bill
    hms.set_appointment_status(11, "Cancelled")

    doctors = list(db.staff.find({"role": "Doctor"}))
    generate_history(rng, doctors, registered)

    depts = {d["dept_id"]: d["name"] for d in db.departments.find()}
    doctor_dept = {d["staff_id"]: depts[d["dept_id"]] for d in doctors}
    for patient, room, doctor, diagnosis, admitted, discharged in ADMISSIONS:
        admission_id = hms.admit_patient(patient, room, doctor, diagnosis, days_ago(admitted))
        if discharged is not None:
            hms.discharge_patient(admission_id, days_ago(discharged))
            if diagnosis not in ("Unstable angina", "Total knee replacement"):   # those have hand-written ones
                hms.add_medical_record(patient, "Discharge Summary",
                                       {"procedure": diagnosis, "follow_up_days": 7},
                                       doctor_id=doctor, recorded_at=days_ago(discharged, "12:00"),
                                       summary_xml=discharge_xml(diagnosis, doctor_dept[doctor], 7))

    for patient, doctor, kind, ago, at, details, xml in RECORDS:
        hms.add_medical_record(patient, kind, details, doctor_id=doctor,
                               recorded_at=days_ago(ago, at), summary_xml=xml)

    # most bills older than a week have been paid, a few days after they were issued
    week_ago = days_ago(7)
    for bill in list(db.bills.find({"bill_date": {"$lt": week_ago}})):
        if rng.random() < 0.85:
            paid = min(bill["bill_date"] + timedelta(days=rng.randint(0, 5)), week_ago)
            hms.pay_bill(bill["bill_id"], paid_on=paid)

    hms.refresh_monthly_revenue()
