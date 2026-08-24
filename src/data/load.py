import pandas as pd
import duckdb
import yaml

def load_raw(state: str = None, year_min: int = 2010, year_max: int = 2016) -> pd.DataFrame:
    with open("config/schema.yaml", "r") as f:
        schema = yaml.safe_load(f)

    file_pattern = "data/raw/csv/cases/*.csv"
    
    col_mapping = {
        'case_id': schema.get('case_id'),
        'filing_date': schema.get('filing_date'),
        'registration_date': schema.get('registration_date'),
        'decision_date': schema.get('decision_date'),
        'case_type': schema.get('case_type'),
        'court_id': schema.get('court_id'),
        'district': schema.get('district'),
        'state': schema.get('state'),
        'act_section': schema.get('act_section'),
        'pending_flag': schema.get('pending_flag'),
        'transfer_flag': schema.get('transfer_flag'),
    }
    
    select_exprs = []
    for std_name, raw_name in col_mapping.items():
        if raw_name:
            if std_name in ['filing_date', 'decision_date', 'registration_date']:
                select_exprs.append(f"TRY_CAST({raw_name} AS DATE) AS {std_name}")
            else:
                select_exprs.append(f"{raw_name} AS {std_name}")
                
    select_clause = ", ".join(select_exprs)
    
    where_parts = []
    if state and schema.get('state'):
        where_parts.append(f"{schema.get('state')} = '{state}'")
        
    year_col = col_mapping['filing_date']
    if year_col:
        where_parts.append(f"year(TRY_CAST({year_col} AS DATE)) BETWEEN {year_min} AND {year_max}")
        
    where_clause = ""
    if where_parts:
        where_clause = "WHERE " + " AND ".join(where_parts)
        
    query = f"""
        SELECT {select_clause}
        FROM read_csv_auto('{file_pattern}', ignore_errors=true)
        {where_clause}
    """
    
    con = duckdb.connect()
    df = con.execute(query).fetchdf()
    return df
