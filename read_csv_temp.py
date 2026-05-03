import pandas as pd

file_path = '/Users/uenomasayuki/Dev/apps/UmaLab/backend/data/keiba_data/001中.CSV'

try:
    df = pd.read_csv(file_path, encoding='shift_jis', header=None)
    print(df.head().to_markdown(index=False))
except Exception as e:
    print(f"Error reading CSV: {e}")
