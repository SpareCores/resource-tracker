from csv import DictReader
from urllib.parse import urlparse
from urllib.request import urlopen

class TinyDataFrame:
    """A very inefficient data-frame implementation with a few features.

    Args:
        data: Dictionary of lists/arrays or list of dictionaries.
        csv_file_path: Path to a CSV file.

    Example:
        >>> df = TinyDataFrame(csv_file_path="https://gist.githubusercontent.com/seankross/a412dfbd88b3db70b74b/raw/5f23f993cd87c283ce766e7ac6b329ee7cc2e1d1/mtcars.csv")
        >>> print(df)
        TinyDataFrame with 32 rows and 12 columns. First row as a dict: {'model': 'Mazda RX4', 'mpg': '21', 'cyl': '6', 'disp': '160', 'hp': '110', 'drat': '3.9', 'wt': '2.62', 'qsec': '16.46', 'vs': '0', 'am': '1', 'gear': '4', 'carb': '4'}
        >>> df[2:5][['model', 'hp']]
        TinyDataFrame with 3 rows and 2 columns. First row as a dict: {'model': 'Datsun 710', 'hp': '93'}
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
        """Read a CSV file and return a list of dictionaries.

        Args:
            csv_file_path: CSV file path or URL.
        """
        results = []

        parsed = urlparse(csv_file_path)
        if parsed.scheme in ('http', 'https'):
            with urlopen(csv_file_path) as response:
                content = response.read().decode('utf-8').splitlines()
                csv_source = content
        else:
            csv_source = open(csv_file_path, "r")

        try:
            reader = DictReader(csv_source)
            for row in reader:
                results.append(row)
        finally:
            if not isinstance(csv_source, list):
                csv_source.close()

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
    
    def __repr__(self):
        """Return a string representation of the data-frame."""
        return f"TinyDataFrame with {len(self)} rows and {len(self.columns)} columns. First row as a dict: {self[0]}"
