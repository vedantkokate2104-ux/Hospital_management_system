// =====================================================================
// Hospital Management System - MongoDB part (NoSQL document store)
// Labs 9 and 10: CRUD, filters, projection, sorting, indexing,
// aggregation, embedded vs referenced document models.
//
// Run:  mongosh mongo/hospital_mongo.js
//   or  mongosh  then  load("mongo/hospital_mongo.js")
//
// Why MongoDB here: lab reports, imaging results and device readings
// have a different shape for every test, so they fit documents better
// than fixed relational columns.
// =====================================================================

db = db.getSiblingDB("hospital_nosql");
db.dropDatabase();

// ---------------------------------------------------------------------
// 1. EMBEDDED model: one document per patient, visits embedded inside
// ---------------------------------------------------------------------
db.patients_embedded.insertMany([
  {
    _id: 1, name: "Rahul Sharma", gender: "Male", blood_group: "B+",
    address: { city: "Mumbai", pincode: "400001" },
    allergies: ["Penicillin"],
    visits: [
      { date: ISODate("2026-08-20"), doctor: "Dr. Anil Mehta", department: "General Medicine",
        diagnosis: "Viral fever", fee: 500,
        lab_tests: [ { test: "CBC", hemoglobin: 13.8, wbc: 11200, platelets: 180000 } ] },
      { date: ISODate("2026-10-16"), doctor: "Dr. Vikram Joshi", department: "General Medicine",
        diagnosis: "Follow-up", fee: 400, lab_tests: [] }
    ]
  },
  {
    _id: 3, name: "Amit Patel", gender: "Male", blood_group: "A+",
    address: { city: "Mumbai", pincode: "400058" },
    allergies: ["Sulfa drugs", "Peanuts"],
    visits: [
      { date: ISODate("2026-08-30"), doctor: "Dr. Sneha Kulkarni", department: "Cardiology",
        diagnosis: "Chest pain on exertion", fee: 1200,
        lab_tests: [
          { test: "Lipid Profile", total_cholesterol: 245, ldl: 165, hdl: 38 },
          { test: "Troponin I", troponin_i: 0.08 }
        ] }
    ]
  },
  {
    _id: 8, name: "Deepa Menon", gender: "Female", blood_group: "O+",
    address: { city: "Mumbai", pincode: "400050" },
    allergies: [],
    visits: [
      { date: ISODate("2026-09-19"), doctor: "Dr. Anil Mehta", department: "General Medicine",
        diagnosis: "Type 2 diabetes", fee: 500,
        lab_tests: [ { test: "HbA1c", hba1c: 7.4 } ] }
    ]
  },
  {
    _id: 9, name: "Arjun Reddy", gender: "Male", blood_group: "B+",
    address: { city: "Pune", pincode: "411004" },
    allergies: ["Latex"],
    visits: [
      { date: ISODate("2026-09-21"), doctor: "Dr. Farhan Shaikh", department: "Neurology",
        diagnosis: "Migraine", fee: 1500, lab_tests: [ { test: "MRI Brain", finding: "Normal" } ] }
    ]
  },
  {
    _id: 13, name: "Manoj Tiwari", gender: "Male", blood_group: "B+",
    address: { city: "Mumbai", pincode: "400070" },
    allergies: ["Penicillin", "Aspirin"],
    visits: [
      { date: ISODate("2026-10-07"), doctor: "Dr. Anil Mehta", department: "General Medicine",
        diagnosis: "Acidity", fee: 500, lab_tests: [] },
      { date: ISODate("2026-10-18"), doctor: "Dr. Anil Mehta", department: "General Medicine",
        diagnosis: "Dengue fever", fee: 500,
        lab_tests: [ { test: "Dengue NS1", ns1: "Positive", platelets: 85000 } ] }
    ]
  }
]);

// ---------------------------------------------------------------------
// 2. REFERENCED model: patients, doctors and visits in separate
//    collections linked by ids (like foreign keys)
// ---------------------------------------------------------------------
db.doctors.insertMany([
  { _id: 1, name: "Dr. Anil Mehta",     department: "General Medicine", fee: 500 },
  { _id: 2, name: "Dr. Sneha Kulkarni", department: "Cardiology",       fee: 1200 },
  { _id: 5, name: "Dr. Farhan Shaikh",  department: "Neurology",        fee: 1500 },
  { _id: 7, name: "Dr. Vikram Joshi",   department: "General Medicine", fee: 400 }
]);

db.patients_ref.insertMany(
  db.patients_embedded.find({}, { visits: 0 }).toArray()
);

db.visits.insertMany([
  { patient_id: 1,  doctor_id: 1, date: ISODate("2026-08-20"), diagnosis: "Viral fever",           fee: 500 },
  { patient_id: 1,  doctor_id: 7, date: ISODate("2026-10-16"), diagnosis: "Follow-up",             fee: 400 },
  { patient_id: 3,  doctor_id: 2, date: ISODate("2026-08-30"), diagnosis: "Chest pain on exertion", fee: 1200 },
  { patient_id: 8,  doctor_id: 1, date: ISODate("2026-09-19"), diagnosis: "Type 2 diabetes",       fee: 500 },
  { patient_id: 9,  doctor_id: 5, date: ISODate("2026-09-21"), diagnosis: "Migraine",              fee: 1500 },
  { patient_id: 13, doctor_id: 1, date: ISODate("2026-10-07"), diagnosis: "Acidity",               fee: 500 },
  { patient_id: 13, doctor_id: 1, date: ISODate("2026-10-18"), diagnosis: "Dengue fever",          fee: 500 }
]);

// ---------------------------------------------------------------------
// 3. CRUD
// ---------------------------------------------------------------------
print("\n--- Create ---");
db.patients_embedded.insertOne({
  _id: 16, name: "Kiran Desai", gender: "Female", blood_group: "O-",
  address: { city: "Navi Mumbai", pincode: "400703" }, allergies: [], visits: []
});

print("\n--- Read: filter + projection + sort ---");
printjson(
  db.patients_embedded
    .find({ "address.city": "Mumbai" }, { _id: 0, name: 1, blood_group: 1 })
    .sort({ name: 1 })
    .toArray()
);

print("\n--- Read: array and nested filters ---");
printjson(db.patients_embedded.find({ allergies: "Penicillin" }, { name: 1 }).toArray());
printjson(db.patients_embedded.find({ "visits.lab_tests.ldl": { $gt: 130 } }, { name: 1 }).toArray());
printjson(db.patients_embedded.find({ $or: [ { blood_group: "O-" }, { blood_group: "AB-" } ] }, { name: 1, blood_group: 1 }).toArray());

print("\n--- Update ---");
db.patients_embedded.updateOne(
  { _id: 16 },
  { $push: { visits: { date: new Date(), doctor: "Dr. Kavita Nair", department: "Dermatology",
                       diagnosis: "Eczema", fee: 800, lab_tests: [] } },
    $addToSet: { allergies: "Dust" } }
);
db.patients_embedded.updateMany({ "address.city": "Pune" }, { $set: { out_of_city: true } });
printjson(db.patients_embedded.findOne({ _id: 16 }));

print("\n--- Delete ---");
db.patients_embedded.deleteOne({ _id: 16 });
print("patients now: " + db.patients_embedded.countDocuments());

// ---------------------------------------------------------------------
// 4. Indexing
// ---------------------------------------------------------------------
db.patients_embedded.createIndex({ "address.city": 1, name: 1 });
db.patients_embedded.createIndex({ allergies: 1 });             // multikey index on an array
db.visits.createIndex({ patient_id: 1, date: -1 });
db.visits.createIndex({ doctor_id: 1 });

print("\n--- Index use (look for IXSCAN instead of COLLSCAN) ---");
const plan = db.patients_embedded.find({ allergies: "Penicillin" }).explain("executionStats");
print("winning stage: " + plan.queryPlanner.winningPlan.inputStage?.stage);
print("docs examined: " + plan.executionStats.totalDocsExamined);

// ---------------------------------------------------------------------
// 5. Aggregation
// ---------------------------------------------------------------------
print("\n--- Revenue per department (embedded model: $unwind) ---");
printjson(db.patients_embedded.aggregate([
  { $unwind: "$visits" },
  { $group: { _id: "$visits.department", visits: { $sum: 1 }, revenue: { $sum: "$visits.fee" } } },
  { $sort: { revenue: -1 } }
]).toArray());

print("\n--- Visits per doctor (referenced model: $lookup = join) ---");
printjson(db.visits.aggregate([
  { $lookup: { from: "doctors", localField: "doctor_id", foreignField: "_id", as: "doctor" } },
  { $unwind: "$doctor" },
  { $group: { _id: "$doctor.name", visits: { $sum: 1 }, revenue: { $sum: "$fee" } } },
  { $sort: { visits: -1 } }
]).toArray());

print("\n--- Patients with an abnormal lab value ---");
printjson(db.patients_embedded.aggregate([
  { $unwind: "$visits" },
  { $unwind: "$visits.lab_tests" },
  { $match: { $or: [
      { "visits.lab_tests.ldl": { $gt: 130 } },
      { "visits.lab_tests.hba1c": { $gt: 6.5 } },
      { "visits.lab_tests.platelets": { $lt: 150000 } } ] } },
  { $project: { _id: 0, name: 1, test: "$visits.lab_tests.test", date: "$visits.date" } }
]).toArray());

print("\n--- Monthly visit count ($dateToString) ---");
printjson(db.visits.aggregate([
  { $group: { _id: { $dateToString: { format: "%Y-%m", date: "$date" } }, visits: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]).toArray());

// ---------------------------------------------------------------------
// 6. Embedded vs referenced: same question, two models
//    "Full history of patient 13"
// ---------------------------------------------------------------------
print("\n--- Embedded: one read, no join ---");
printjson(db.patients_embedded.findOne({ _id: 13 }, { name: 1, visits: 1 }));

print("\n--- Referenced: needs $lookup to join the collections ---");
printjson(db.patients_ref.aggregate([
  { $match: { _id: 13 } },
  { $lookup: { from: "visits", localField: "_id", foreignField: "patient_id", as: "visits" } },
  { $project: { name: 1, "visits.date": 1, "visits.diagnosis": 1 } }
]).toArray());

// Embedded:   + one read returns everything, atomic updates per patient
//             - document grows with every visit (16 MB limit), doctor data duplicated
// Referenced: + no duplication, visits can be queried on their own, unbounded growth is fine
//             - reading a full history needs a $lookup (join)
