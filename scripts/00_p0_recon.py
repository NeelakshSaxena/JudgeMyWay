import os
import glob
import duckdb
import yaml
import textwrap

def run_recon():
    print("Starting P0 Recon & Schema Discovery...")
    
    # Load schema
    with open("config/schema.yaml", "r") as f:
        schema = yaml.safe_load(f)
    
    report_lines = ["# P0 Recon & Schema Discovery Report\n"]
    
    # 1. File list with sizes
    report_lines.append("## 1. Files in data/raw/\n")
    for root, dirs, files in os.walk("data/raw"):
        for name in files:
            filepath = os.path.join(root, name)
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            report_lines.append(f"- `{filepath}`: {size_mb:.2f} MB")
            
    # For exploration, we'll try to find the actual case CSV file inside data/raw/csv/cases
    # Since it might be tar.gz, DuckDB can read csv.gz directly but not tar.gz natively easily.
    # We will assume there's an extracted csv somewhere, or try to read csv/cases/cases.tar.gz
    # Wait, DevDataLab cases are usually zipped. Let's look for any .csv file.
    csv_files = glob.glob("data/raw/**/*.csv", recursive=True)
    case_files = [f for f in csv_files if "cases" in f.lower()]
    
    if not case_files:
        print("Could not find an extracted cases CSV file. Please extract the cases tar.gz into data/raw/csv/cases/ first!")
        report_lines.append("\n**ERROR: Could not find an extracted cases CSV file.**")
        with open("outputs/p0_recon.md", "w") as f:
            f.write("\n".join(report_lines))
        return

    main_csv = case_files[0]
    report_lines.append(f"\n## Analyzing File: `{main_csv}`\n")
    
    con = duckdb.connect(database=':memory:')
    
    # 2. Columns
    # Read a sample to get headers
    sample_df = con.execute(f"SELECT * FROM read_csv_auto('{main_csv}', sample_size=10000) LIMIT 1").fetchdf()
    actual_columns = set(sample_df.columns)
    
    report_lines.append("## 2. Column Mapping Check\n")
    mapped_columns = [v for k, v in schema.items() if isinstance(v, str) and k not in ['date_format', 'data_cutoff'] and v]
    mapped_columns += schema.get('drop_columns', [])
    
    missing_mappings = []
    for col in mapped_columns:
        if col not in actual_columns:
            missing_mappings.append(col)
            report_lines.append(f"- **FLAG**: Mapped column `{col}` NOT FOUND in real data.")
        else:
            report_lines.append(f"- `{col}` -> Found")
            
    # 3. Row count
    print("Counting rows...")
    row_count = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{main_csv}')").fetchone()[0]
    report_lines.append(f"\n## 3. Row Count\n- {row_count:,} rows in {main_csv}\n")
    
    # 4. Required fields
    print("Analyzing required fields...")
    req_fields = {
        'filing_date': schema.get('filing_date'),
        'decision_date': schema.get('decision_date'),
        'case_type': schema.get('case_type'),
        'court_id': schema.get('court_id')
    }
    
    report_lines.append("## 4. Required Fields Analysis\n")
    for req_k, actual_col in req_fields.items():
        if not actual_col or actual_col not in actual_columns:
            report_lines.append(f"### {req_k} (`{actual_col}`)\n**MISSING IN DATASET**\n")
            continue
            
        stats = con.execute(f"""
            SELECT 
                COUNT(*) FILTER (WHERE "{actual_col}" IS NULL) * 1.0 / COUNT(*) as null_rate,
                COUNT(DISTINCT "{actual_col}") as dist_count,
                MIN("{actual_col}") as min_val,
                MAX("{actual_col}") as max_val
            FROM read_csv_auto('{main_csv}', sample_size=10000)
        """).fetchone()
        
        examples = con.execute(f"""
            SELECT "{actual_col}" FROM read_csv_auto('{main_csv}', sample_size=10000)
            WHERE "{actual_col}" IS NOT NULL LIMIT 5
        """).fetchall()
        
        report_lines.append(f"### {req_k} (`{actual_col}`)")
        report_lines.append(f"- Null rate: {stats[0]:.2%}")
        report_lines.append(f"- Distinct count: {stats[1]:,}")
        report_lines.append(f"- Range: {stats[2]} to {stats[3]}")
        report_lines.append(f"- Examples: {[e[0] for e in examples]}\n")
        
    # 5. Max decision date (data_cutoff)
    print("Finding data cutoff...")
    dec_col = schema.get('decision_date')
    if dec_col in actual_columns:
        # Assuming format allows string max for iso dates, else parse. DevDataLab uses YYYY-MM-DD
        max_date_raw = con.execute(f"SELECT MAX({dec_col}) FROM read_csv_auto('{main_csv}')").fetchone()[0]
        max_date = str(max_date_raw) if max_date_raw is not None else ""
        report_lines.append(f"## 5. Data Cutoff\n- True maximum decision_date: `{max_date}`\n")
        # Update schema.yaml
        schema['data_cutoff'] = max_date
        with open("config/schema.yaml", "w") as f:
            yaml.dump(schema, f, sort_keys=False)
            
    # 6. Presence checks
    report_lines.append("## 6. Presence Checks for Implicit Information\n")
    # check for gender/judge/disposition
    gender_cols = [c for c in actual_columns if 'gender' in c.lower() or 'female' in c.lower()]
    judge_cols = [c for c in actual_columns if 'judge' in c.lower()]
    disp_cols = [c for c in actual_columns if 'disp' in c.lower() or 'outcome' in c.lower() or 'status' in c.lower()]
    
    report_lines.append(f"- Gender columns found: {gender_cols}")
    report_lines.append(f"- Judge columns found: {judge_cols}")
    report_lines.append(f"- Disposition/Status columns found: {disp_cols}\n")
    
    # 7. Censoring share
    if dec_col in actual_columns:
        cen_share = con.execute(f"SELECT COUNT(*) FILTER (WHERE {dec_col} IS NULL) * 1.0 / COUNT(*) FROM read_csv_auto('{main_csv}')").fetchone()[0]
        report_lines.append(f"## 7. Censoring\n- Estimated share of rows missing decision_date (censored): {cen_share:.2%}\n")
        
    with open("outputs/p0_recon.md", "w") as f:
        f.write("\n".join(report_lines))
        
    print("Recon complete! Report written to outputs/p0_recon.md")

if __name__ == "__main__":
    run_recon()
