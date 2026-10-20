-- =====================================================================
-- 06_xml_json_queries.sql : semi-structured data
-- (Lab 8: XML, XPath, XQuery-style queries and JSON functions)
-- Run after the sample data:  \i database/06_xml_json_queries.sql
-- =====================================================================
SET search_path TO hms, public;

-- ---------------------------------------------------------------------
-- JSON / JSONB
-- ---------------------------------------------------------------------

-- 1. Read fields out of the JSON document ( -> returns json, ->> returns text )
SELECT p.first_name || ' ' || p.last_name AS patient,
       m.details ->> 'test'              AS test,
       m.details -> 'results'            AS results,
       m.details ->> 'flag'              AS flag
  FROM medical_records m
  JOIN patients p USING (patient_id)
 WHERE m.record_type = 'Lab Report';

-- 2. Containment (@>) uses the GIN index idx_records_details
SELECT record_id, patient_id, details ->> 'test' AS test
  FROM medical_records
 WHERE details @> '{"flag": "High"}';

-- 3. Numeric condition inside the document: LDL above 130
SELECT patient_id, (details #>> '{results,ldl}')::int AS ldl
  FROM medical_records
 WHERE details ->> 'test' = 'Lipid Profile'
   AND (details #>> '{results,ldl}')::int > 130;

-- 4. SQL/JSON path language
SELECT patient_id, details ->> 'test' AS test
  FROM medical_records
 WHERE details @? '$.results.platelets ? (@ < 150000)';

-- 5. Expand a JSON object into rows
SELECT m.record_id, r.key AS parameter, r.value AS value
  FROM medical_records m,
       jsonb_each(m.details -> 'results') AS r
 WHERE m.details ->> 'test' = 'Lipid Profile';

-- 6. Build JSON from relational data
SELECT fn_patient_json(3);

SELECT jsonb_agg(jsonb_build_object('doctor', doctor_name, 'fee', consultation_fee)
                 ORDER BY consultation_fee DESC) AS doctors_by_fee
  FROM v_doctor_directory;

-- 7. Composite type and array columns as JSON
SELECT first_name, to_jsonb(address) AS address, to_jsonb(allergies) AS allergies
  FROM patients WHERE cardinality(allergies) > 0;

-- ---------------------------------------------------------------------
-- XML
-- ---------------------------------------------------------------------

-- 8. XPath: pull values out of the discharge summaries
SELECT record_id,
       (xpath('/discharge_summary/diagnosis/text()', summary_xml))[1]::text AS diagnosis,
       (xpath('/discharge_summary/follow_up/@days', summary_xml))[1]::text  AS follow_up_days
  FROM medical_records
 WHERE summary_xml IS NOT NULL;

-- 9. XPath returning many nodes -> one row per medicine
SELECT m.record_id,
       (xpath('text()', med))[1]::text  AS medicine,
       (xpath('@dose', med))[1]::text   AS dose,
       (xpath('@frequency', med))[1]::text AS frequency
  FROM medical_records m,
       unnest(xpath('/discharge_summary/medications/medicine', m.summary_xml)) AS med
 WHERE m.summary_xml IS NOT NULL;

-- 10. Filter with an XPath predicate (XQuery-like WHERE)
SELECT record_id, patient_id
  FROM medical_records
 WHERE xpath_exists('/discharge_summary/medications/medicine[text()="Clopidogrel"]', summary_xml);

-- 11. XMLTABLE: shred XML into a relational result (SQL/XML standard)
SELECT m.record_id, x.*
  FROM medical_records m,
       XMLTABLE('/discharge_summary/medications/medicine'
                PASSING m.summary_xml
                COLUMNS medicine  TEXT PATH 'text()',
                        dose      TEXT PATH '@dose',
                        frequency TEXT PATH '@frequency') AS x
 WHERE m.summary_xml IS NOT NULL;

-- 12. Publish relational data as XML
SELECT fn_patient_xml(3);

SELECT xmlelement(name departments,
         xmlagg(xmlelement(name department,
                  xmlattributes(dept_id AS id, floor_no AS floor), name)
                ORDER BY dept_id))
  FROM departments;

-- 13. Whole query result as XML in one call
SELECT query_to_xml('SELECT doctor_name, specialization, consultation_fee FROM hms.v_doctor_directory',
                    true, false, '');
