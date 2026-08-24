# P0 Recon & Schema Discovery Report

## 1. Files in data/raw/

- `data/raw\.gitkeep`: 0.00 MB
- `data/raw\justice_data.zip`: 4890.69 MB
- `data/raw\license.txt`: 0.02 MB
- `data/raw\README.md`: 0.00 MB
- `data/raw\csv\acts_sections.csv`: 3403.55 MB
- `data/raw\csv\judges_clean.csv`: 7.96 MB
- `data/raw\csv\judges_clean.tar`: 7.96 MB
- `data/raw\csv\judges_clean.tar.gz`: 0.84 MB
- `data/raw\csv\cases\cases.tar.gz`: 1343.56 MB
- `data/raw\csv\cases\cases_2010.csv`: 817.29 MB
- `data/raw\csv\cases\cases_2011.csv`: 995.51 MB
- `data/raw\csv\cases\cases_2012.csv`: 1223.55 MB
- `data/raw\csv\cases\cases_2013.csv`: 1444.17 MB
- `data/raw\csv\cases\cases_2014.csv`: 1694.62 MB
- `data/raw\csv\cases\cases_2015.csv`: 2000.52 MB
- `data/raw\csv\cases\cases_2016.csv`: 2161.17 MB
- `data/raw\csv\cases\cases_2017.csv`: 2485.44 MB
- `data/raw\csv\cases\cases_2018.csv`: 2591.45 MB
- `data/raw\csv\keys\keys.tar.gz`: 63.41 MB
- `data/raw\dta\acts_sections.tar.gz`: 503.51 MB
- `data/raw\dta\judges_clean.tar.gz`: 2.61 MB
- `data/raw\dta\cases\cases.tar.gz`: 2320.47 MB
- `data/raw\dta\keys\keys.tar.gz`: 115.11 MB

## Analyzing File: `data/raw\csv\cases\cases_2010.csv`

## 2. Column Mapping Check

- `ddl_case_id` -> Found
- `date_of_filing` -> Found
- `date_of_decision` -> Found
- `type_name` -> Found
- `court_no` -> Found
- `dist_code` -> Found
- `state_code` -> Found
- `judge_position` -> Found
- `female_defendant` -> Found
- `female_petitioner` -> Found
- `female_adv_def` -> Found
- `female_adv_pet` -> Found
- `disp_name` -> Found
- `purpose_name` -> Found

## 3. Row Count
- 4,281,327 rows in data/raw\csv\cases\cases_2010.csv

## 4. Required Fields Analysis

### filing_date (`date_of_filing`)
- Null rate: 0.00%
- Distinct count: 365
- Range: 2010-01-01 to 2010-12-31
- Examples: [datetime.date(2010, 12, 13), datetime.date(2010, 2, 25), datetime.date(2010, 2, 25), datetime.date(2010, 2, 25), datetime.date(2010, 2, 25)]

### decision_date (`date_of_decision`)
- Null rate: 13.33%
- Distinct count: 4,269
- Range: 0001-11-11 to 7201-10-15
- Examples: [datetime.date(2011, 6, 19), datetime.date(2010, 11, 21), datetime.date(2010, 11, 21), datetime.date(2010, 11, 21), datetime.date(2010, 11, 21)]

### case_type (`type_name`)
- Null rate: 0.00%
- Distinct count: 5,452
- Range: 1 to 5452
- Examples: [790, 2587, 2587, 2587, 2587]

### court_id (`court_no`)
- Null rate: 0.00%
- Distinct count: 68
- Range: 01 to 75
- Examples: ['01', '01', '01', '01', '01']

## 5. Data Cutoff
- True maximum decision_date: `2029-12-30`

## 6. Presence Checks for Implicit Information

- Gender columns found: ['female_defendant', 'female_petitioner', 'female_adv_def', 'female_adv_pet']
- Judge columns found: ['judge_position']
- Disposition/Status columns found: ['disp_name']

## 7. Censoring
- Estimated share of rows missing decision_date (censored): 13.33%
