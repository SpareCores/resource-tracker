"""
A very inefficient data-frame implementation for manipulating resource usage data.
"""

from csv import QUOTE_MINIMAL, QUOTE_NONNUMERIC, DictReader
from csv import writer as csv_writer
from io import StringIO
from typing import Optional, Union
from urllib.parse import urlparse
from urllib.request import urlopen


class TinyDataFrame:
    """A very inefficient data-frame implementation with a few features.

    Supported features:

    - reading CSV files from a remote URL
    - reading CSV files from a local file
    - converting a dictionary of lists/arrays to a data-frame
    - converting a list of dictionaries to a data-frame
    - slicing rows
    - slicing columns
    - slicing rows and columns
    - printing a summary of the data-frame
    - printing the data-frame as a human-readable (grid) table
    - renaming columns
    - writing to a CSV file

    Args:
        data: Dictionary of lists/arrays or list of dictionaries.
        csv_file_path: Path to a properly quoted CSV file.

    Example:

        >>> df = TinyDataFrame(csv_file_path="https://raw.githubusercontent.com/plotly/datasets/refs/heads/master/mtcars.csv")
        >>> df
        TinyDataFrame with 32 rows and 12 columns. First row as a dict: {'manufacturer': 'Mazda RX4', 'mpg': 21.0, 'cyl': 6.0, 'disp': 160.0, 'hp': 110.0, 'drat': 3.9, 'wt': 2.62, 'qsec': 16.46, 'vs': 0.0, 'am': 1.0, 'gear': 4.0, 'carb': 4.0}
        >>> df[2:5][['manufacturer', 'hp']]
        TinyDataFrame with 3 rows and 2 columns. First row as a dict: {'manufacturer': 'Datsun 710', 'hp': 93.0}
        >>> print(df[2:5][['manufacturer', 'hp']])  # doctest: +NORMALIZE_WHITESPACE
        TinyDataFrame with 3 rows and 2 columns:
        manufacturer      | hp
        ------------------+------
        Datsun 710        |  93.0
        Hornet 4 Drive    | 110.0
        Hornet Sportabout | 175.0
        >>> print(df[2:5][['manufacturer', 'hp']].to_csv())  # doctest: +NORMALIZE_WHITESPACE
        "manufacturer","hp"
        "Datsun 710",93.0
        "Hornet 4 Drive",110.0
        "Hornet Sportabout",175.0
    """

    def __init__(
        self, data: Optional[dict | list] = None, csv_file_path: Optional[str] = None
    ):
        """
        Initialize with either:

        - Dictionary of lists/arrays
        - List of dictionaries
        - CSV file path
        """
        self.columns = []
        self._data = {}

        assert data is not None or csv_file_path is not None, (
            "either data or csv_file_path must be provided"
        )
        assert data is None or csv_file_path is None, (
            "only one of data or csv_file_path must be provided"
        )
        assert data is None or isinstance(data, dict) or isinstance(data, list), (
            "data must be a dictionary or a list"
        )
        assert csv_file_path is None or isinstance(csv_file_path, str), (
            "csv_file_path must be a string"
        )

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

    def _read_csv(self, csv_file_path: str) -> list[dict]:
        """Read a CSV file and return a list of dictionaries.

        Args:
            csv_file_path: CSV file path or URL.
        """
        results = []

        parsed = urlparse(csv_file_path)
        if parsed.scheme in ("http", "https"):
            with urlopen(csv_file_path) as response:
                content = response.read().decode("utf-8").splitlines()
                csv_source = content
        else:
            csv_source = open(csv_file_path, "r")

        try:
            reader = DictReader(csv_source, quoting=QUOTE_NONNUMERIC)
            for row in reader:
                results.append(row)
        finally:
            if not isinstance(csv_source, list):
                csv_source.close()

        return results

    def __len__(self):
        """Return the number of rows in the data-frame"""
        return len(next(iter(self._data.values()))) if self.columns else 0

    def __getitem__(
        self, key: Union[str, list[str], int, slice]
    ) -> Union[list, dict, "TinyDataFrame"]:
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

    def __setitem__(self, key: str, value: list) -> None:
        """Set a column with the given key to the provided values.

        Args:
            key: Column name (string)
            value: List of values for the column

        Raises:
            TypeError: If key is not a string
            ValueError: If the length of values doesn't match the dataframe length
        """
        if not isinstance(key, str):
            raise TypeError(f"Column name must be a string, got {type(key)}")

        if len(self) > 0 and len(value) != len(self):
            raise ValueError(
                f"Length of values ({len(value)}) must match dataframe length ({len(self)})"
            )

        if key not in self.columns:
            self.columns.append(key)

        self._data[key] = list(value)

    def head(self, n: int = 5) -> "TinyDataFrame":
        """Return first n rows as a new TinyDataFrame."""
        return self[slice(0, n)]

    def tail(self, n: int = 5) -> "TinyDataFrame":
        """Return last n rows as a new TinyDataFrame."""
        return self[slice(-n, None)]

    def __repr__(self) -> str:
        """Return a string representation of the data-frame."""
        return f"TinyDataFrame with {len(self)} rows and {len(self.columns)} columns. First row as a dict: {self[0]}"

    def __str__(self) -> str:
        """Print the first 10 rows of the data-frame in a human-readable table."""
        header = (
            f"TinyDataFrame with {len(self)} rows and {len(self.columns)} columns:\n"
        )
        if len(self) == 0:
            return header + "Empty dataframe"

        max_rows = min(10, len(self))

        col_widths = {}
        for col in self.columns:
            col_widths[col] = len(str(col))
            for i in range(max_rows):
                col_widths[col] = max(col_widths[col], len(str(self._data[col][i])))

        rows = []
        header_row = " | ".join(str(col).ljust(col_widths[col]) for col in self.columns)
        rows.append(header_row)
        separator = "-+-".join("-" * col_widths[col] for col in self.columns)
        rows.append(separator)

        for i in range(max_rows):
            row_values = []
            for col in self.columns:
                value = str(self._data[col][i])
                # right-align numbers, left-align strings
                try:
                    float(value)  # check if it's a number
                    row_values.append(value.rjust(col_widths[col]))
                except ValueError:
                    row_values.append(value.ljust(col_widths[col]))
            rows.append(" | ".join(row_values))

        # add ellipsis if there are more rows
        if len(self) > max_rows:
            rows.append("..." + " " * (len(rows[0]) - 3))
        return header + "\n".join(rows)

    def to_csv(
        self, csv_file_path: Optional[str] = None, quote_strings: bool = True
    ) -> str:
        """Write the data-frame to a CSV file or return as string if no path is provided.

        Args:
            csv_file_path: Path to write CSV file. If None, returns CSV as string.
            quote_strings: Whether to quote strings.
        """
        if csv_file_path:
            f = open(csv_file_path, "w", newline="")
        else:
            f = StringIO(newline="")

        try:
            writer = csv_writer(
                f, quoting=QUOTE_NONNUMERIC if quote_strings else QUOTE_MINIMAL
            )
            writer.writerow(self.columns)
            for i in range(len(self)):
                writer.writerow([self._data[col][i] for col in self.columns])

            if not csv_file_path:
                return f.getvalue()
        finally:
            f.close()

    def rename(self, columns: dict) -> "TinyDataFrame":
        """Rename one or multiple columns.

        Args:
            columns: Dictionary mapping old column names to new column names.

        Returns:
            Self for method chaining.

        Raises:
            KeyError: If any old column name doesn't exist in the dataframe.
        """
        for old_name in columns.keys():
            if old_name not in self.columns:
                raise KeyError(f"Column '{old_name}' not found in dataframe")

        for i, col in enumerate(self.columns):
            if col in columns:
                self.columns[i] = columns[col]
        # note that order of columns might change, but self.columns matters anyway
        for old_name, new_name in columns.items():
            self._data[new_name] = self._data.pop(old_name)

        return self
