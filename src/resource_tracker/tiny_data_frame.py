from csv import DictReader

class TinyDataFrame:
    """A tiny data-frame implementation with a few features.

    Args:
        data: Dictionary of lists/arrays or list of dictionaries.
    """

    def __init__(self, data=None, csv_file_path=None):
        """
        Initialize with either:
        - Dictionary of lists/arrays
        - List of dictionaries
        - CSV file path
        """
        self.columns = []
        self._data = {}

        assert data is not None or csv_file_path is not None, "either data or csv_file_path must be provided"
        assert data is None or csv_file_path is None, "only one of data or csv_file_path must be provided"
        assert data is None or isinstance(data, dict) or isinstance(data, list), "data must be a dictionary or a list"
        assert csv_file_path is None or isinstance(csv_file_path, str), "csv_file_path must be a string"

        if csv_file_path:
            data = self._read_csv(csv_file_path)

        if isinstance(data, dict):
            self._data = {k: list(v) for k, v in data.items()}
            self.columns = list(self._data.keys())
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            # let's preserve column order
            self.columns = []
            seen_columns = set()
            for row in data:
                for col in row.keys():
                    if col not in seen_columns:
                        self.columns.append(col)
                        seen_columns.add(col)
            self._data = {col: [row.get(col) for row in data] for col in self.columns}

    def _read_csv(self, csv_file_path):
        """Read a CSV file and return a list of dictionaries."""
        results = []
        with open(csv_file_path, "r") as f:
            reader = DictReader(f)
            for row in reader:
                results.append(row)
        return results

    def __len__(self):
        """Return the number of rows in the data-frame"""
        return len(next(iter(self._data.values()))) if self.columns else 0

    def __getitem__(self, key):
        """Get a single column or multiple columns or a row or a slice of rows. Can be chained.

        Args:
            key: A single column name, a list of column names, a row index, or a slice of row indexes.

        Returns:
            A single column as a list, a list of columns as a new TinyDataFrame, a row as a dictionary, or a slice of rows as a new TinyDataFrame.
        """
        # a single column
        if isinstance(key, str):
            return self._data[key]
        # multiple columns
        elif isinstance(key, list) and all(isinstance(k, str) for k in key):
            return TinyDataFrame(
                {col: self._data[col] for col in key if col in self._data}
            )
        # row index
        elif isinstance(key, int):
            return {col: self._data[col][key] for col in self.columns}
        # row indexes
        elif isinstance(key, slice):
            return TinyDataFrame({col: self._data[col][key] for col in self.columns})
        else:
            raise TypeError(f"Invalid key type: {type(key)}")

    def head(self, n=5):
        """Return first n rows as a new TinyDataFrame."""
        return self[slice(0, n)]

    def tail(self, n=5):
        """Return last n rows as a new TinyDataFrame."""
        return self[slice(-n, None)]
