from pathlib import Path
from typing import Tuple
import pandas as pd


def load_dataset(file_path: str) -> pd.DataFrame:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".csv":
        try:
            return pd.read_csv(path)
        except UnicodeDecodeError:
            try:
                return pd.read_csv(path, encoding="latin1")
            except UnicodeDecodeError:
                return pd.read_csv(path, encoding="cp1252")

    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(path)

    if suffix == ".parquet":
        return pd.read_parquet(path)

    raise ValueError("Only CSV, Excel (.xlsx, .xls), and Parquet files are supported.")


def save_dataset(df: pd.DataFrame, file_path: str) -> str:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    suffix = path.suffix.lower()
    
    if suffix == ".csv":
        df.to_csv(path, index=False)
    elif suffix in [".xlsx", ".xls"]:
        df.to_excel(path, index=False)
    elif suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)
    
    return str(path)


def get_dataset_info(file_path: str) -> dict:
    df = load_dataset(file_path)
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "file_size_bytes": Path(file_path).stat().st_size,
        "dtypes": df.dtypes.astype(str).to_dict(),
        "memory_usage_bytes": df.memory_usage(deep=True).sum()
    }