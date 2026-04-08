from statistics import mean
from unittest.mock import MagicMock, patch

import pytest

from resource_tracker.tiny_data_frame import DictReader, StatSpec, TinyDataFrame


@pytest.fixture
def sample_data():
    """Fixture providing sample data for tests"""
    base_timestamp = 1737676800
    diff_timestamp = 3600

    return {
        "timestamp": [
            base_timestamp,
            base_timestamp + diff_timestamp,
            base_timestamp + 2 * diff_timestamp,
            base_timestamp + 3 * diff_timestamp,
            base_timestamp + 4 * diff_timestamp,
            base_timestamp + 5 * diff_timestamp,
            base_timestamp + 6 * diff_timestamp,
            base_timestamp + 7 * diff_timestamp,
            base_timestamp + 8 * diff_timestamp,
            base_timestamp + 9 * diff_timestamp,
            base_timestamp + 10 * diff_timestamp,
            base_timestamp + 11 * diff_timestamp,
        ],
        "cpu": [
            15.5,
            25.3,
            38.7,
            52.4,
            78.2,
            92.7,
            76.8,
            58.3,
            42.1,
            32.6,
            22.4,
            18.9,
        ],
        "memory": [
            2500,
            2700,
            3100,
            3600,
            4200,
            4800,
            4500,
            4100,
            3800,
            3400,
            3000,
            2800,
        ],
    }


def test_initialization_with_dict_of_lists(sample_data):
    """Test TinyDataFrame initialization with a dict of lists"""
    df = TinyDataFrame(sample_data)
    assert df.columns == ["timestamp", "cpu", "memory"]
    assert len(df) == 12


def test_initialization_with_list_of_dicts(sample_data):
    """Test TinyDataFrame initialization with a list of dicts"""
    sample_data_list = [
        {k: sample_data[k][i] for k in sample_data.keys()}
        for i in range(len(next(iter(sample_data.values()))))
    ]
    df = TinyDataFrame(sample_data_list)
    assert df.columns == ["timestamp", "cpu", "memory"]
    assert len(df) == 12


def test_initialization(sample_data):
    """Test TinyDataFrame initialization"""
    df = TinyDataFrame(sample_data)

    # Check columns
    assert df.columns == ["timestamp", "cpu", "memory"]

    # Check length
    assert len(df) == 12

    # Check data integrity
    assert df["timestamp"][0] == 1737676800
    assert df["cpu"][5] == 92.7
    assert df["memory"][11] == 2800


def test_single_column_access(sample_data):
    """Test accessing a single column"""
    df = TinyDataFrame(sample_data)

    # Get a single column
    cpu_data = df["cpu"]

    # Check it's the right data
    assert len(cpu_data) == 12
    assert cpu_data[5] == 92.7
    assert max(cpu_data) == 92.7


def test_multiple_column_access(sample_data):
    """Test accessing multiple columns"""
    df = TinyDataFrame(sample_data)

    # Get multiple columns
    subset = df[["timestamp", "cpu"]]

    # Check it's a TinyDataFrame
    assert isinstance(subset, TinyDataFrame)

    # Check it has the right columns
    assert subset.columns == ["timestamp", "cpu"]

    # Check it has the right data
    assert len(subset) == 12
    assert subset["cpu"][5] == 92.7


def test_row_access(sample_data):
    """Test accessing a single row"""
    df = TinyDataFrame(sample_data)

    # Get a single row
    row = df[5]

    # Check it's a dictionary
    assert isinstance(row, dict)

    # Check it has the right data
    assert row["timestamp"] == 1737676800 + 18000
    assert row["cpu"] == 92.7
    assert row["memory"] == 4800


def test_slice_access(sample_data):
    """Test accessing a slice of rows"""
    df = TinyDataFrame(sample_data)

    # Get a slice of rows
    subset = df[3:6]

    # Check it's a TinyDataFrame
    assert isinstance(subset, TinyDataFrame)

    # Check it has the right length
    assert len(subset) == 3

    # Check it has the right data
    assert subset["cpu"][0] == 52.4
    assert subset["cpu"][2] == 92.7


def test_head_and_tail(sample_data):
    """Test head and tail methods"""
    df = TinyDataFrame(sample_data)

    # Test head
    head_df = df.head(3)
    assert len(head_df) == 3
    assert head_df["cpu"][0] == 15.5
    assert head_df["cpu"][2] == 38.7

    # Test tail
    tail_df = df.tail(3)
    assert len(tail_df) == 3
    assert tail_df["cpu"][0] == 32.6
    assert tail_df["cpu"][2] == 18.9


def test_empty_dataframe():
    """Test creating an empty dataframe"""
    df = TinyDataFrame([])
    assert len(df) == 0
    assert df.columns == []


def test_invalid_access():
    """Test invalid access patterns"""
    df = TinyDataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    # Test invalid column name
    with pytest.raises(KeyError):
        _ = df["non_existent"]
    with pytest.raises(KeyError):
        _ = df[["non_existent1", "non_existent2"]]

    # Test invalid key type
    with pytest.raises(TypeError):
        _ = df[1.5]


def test_chained_operations(sample_data):
    """Test chaining operations"""
    df = TinyDataFrame(sample_data)

    # Chain multiple operations
    result = df[["cpu", "memory"]][3:6]["cpu"]

    # Check the result
    assert result == [52.4, 78.2, 92.7]


def test_csv(tmp_path, sample_data):
    """Test TinyDataFrame writing to and initialization from a CSV file"""
    df = TinyDataFrame(sample_data)
    columns = df.columns

    # Create a temporary CSV file using sample_data
    csv_path = tmp_path / "test_data.csv"
    df.to_csv(csv_path)

    # Initialize TinyDataFrame from CSV
    df = TinyDataFrame(csv_file_path=str(csv_path))

    # Check columns
    assert df.columns == columns

    # Check length
    assert len(df) == len(sample_data[columns[0]])

    # Check data integrity
    assert df[columns[0]][0] == sample_data[columns[0]][0]
    assert df[columns[1]][5] == sample_data[columns[1]][5]
    assert df[columns[2]][11] == sample_data[columns[2]][11]


def test_csv_numeric_types(tmp_path):
    """Test that numeric types are preserved when writing and reading CSV files"""
    # Create a dataframe with mixed types
    original_df = TinyDataFrame(
        {
            "string_col": ["a", "b", "c", "d"],
            "int_col": [1, 2, 3, 4],
            "float_col": [1.1, 2.2, 3.3, 4.4],
        }
    )

    # Write to CSV
    csv_path = tmp_path / "numeric_test.csv"
    original_df.to_csv(csv_path)

    # Read back from CSV
    loaded_df = TinyDataFrame(csv_file_path=str(csv_path))

    # Check that types are preserved
    assert isinstance(loaded_df["string_col"][0], str)
    assert isinstance(loaded_df["int_col"][0], int)  # integers must survive the round-trip as int
    assert isinstance(loaded_df["float_col"][0], float)

    # Check values
    assert loaded_df["string_col"] == ["a", "b", "c", "d"]
    assert loaded_df["int_col"] == [1, 2, 3, 4]
    assert loaded_df["float_col"] == [1.1, 2.2, 3.3, 4.4]

    # Verify the actual CSV format with proper quoting
    with open(csv_path, "r") as f:
        content = f.read()
        # Strings should be quoted, numbers should not
        assert '"string_col"' in content
        assert '"a"' in content
        assert "1," in content  # Unquoted number
        assert "1,1.1" in content  # Unquoted float


def test_set_column(sample_data):
    """Test setting a column using the __setitem__ method"""
    df = TinyDataFrame(sample_data)

    # Test adding a new column
    df["new_column"] = [i * 10 for i in range(12)]

    # Check the column was added
    assert "new_column" in df.columns
    assert len(df.columns) == 4  # original 3 + new one
    assert df["new_column"] == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110]

    # Test modifying an existing column
    df["cpu"] = [i + 5 for i in range(12)]

    # Check the column was modified
    assert df["cpu"] == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]

    # Test error cases
    # Wrong length
    with pytest.raises(ValueError):
        df["error_column"] = [1, 2, 3]  # Too short

    # Wrong key type
    with pytest.raises(TypeError):
        df[123] = [0] * 12  # Non-string key

    # Test sequential operations
    df["new_column"] = [99] * 12
    assert df["new_column"] == [99] * 12


def test_str_representation(sample_data):
    """Test the string representation of TinyDataFrame"""
    df = TinyDataFrame(sample_data)

    # Get the string representation
    str_repr = str(df)

    # Check that it contains the expected header information
    assert (
        f"TinyDataFrame with {len(df)} rows and {len(df.columns)} columns:" in str_repr
    )

    # Check that all column names are in the string representation
    for col in df.columns:
        assert col in str_repr

    # Check that the separator line exists
    assert "-+-" in str_repr

    # Check that some data values are present
    assert "15.5" in str_repr  # First CPU value
    assert "92.7" in str_repr  # Peak CPU value

    # Test with a smaller dataframe to check exact formatting
    small_df = df.head(3)
    small_str = str(small_df)

    # Check the header row and separator are properly formatted
    lines = small_str.split("\n")
    assert "timestamp" in lines[1] and "cpu" in lines[1] and "memory" in lines[1]
    assert "-+-" in lines[2]

    # Check that the data rows contain the expected values
    assert "15.5" in lines[3]  # First row
    assert "25.3" in lines[4]  # Second row
    assert "38.7" in lines[5]  # Third row

    # Test with an empty dataframe
    empty_df = TinyDataFrame([])
    assert "Empty dataframe" in str(empty_df)

    # Test with a dataframe that has more than 10 rows
    # It should only show 10 rows and then an ellipsis
    assert "..." in str(df)


def test_rename_columns(sample_data):
    """Test renaming columns using the rename method"""
    df = TinyDataFrame(sample_data)

    # Original column order
    original_columns = df.columns.copy()
    assert original_columns == ["timestamp", "cpu", "memory"]

    # Test renaming a single column
    df_single = df.rename({"cpu": "processor"})

    # Check that it returns self for chaining
    assert df_single is df

    # Check the column was renamed
    assert "processor" in df.columns
    assert "cpu" not in df.columns
    assert df.columns == ["timestamp", "processor", "memory"]

    # Check that data is preserved
    assert df["processor"][5] == 92.7

    # Test renaming multiple columns
    df = TinyDataFrame(sample_data)  # Reset
    df_multi = df.rename({"timestamp": "time", "memory": "ram"})

    # Check columns were renamed
    assert df_multi.columns == ["time", "cpu", "ram"]

    # Check data integrity
    assert df["time"][0] == 1737676800
    assert df["ram"][11] == 2800

    # Test column order preservation with multiple renames
    df = TinyDataFrame(sample_data)  # Reset
    df.rename({"timestamp": "time", "cpu": "processor", "memory": "ram"})

    # Check order is preserved (just with new names)
    assert df.columns == ["time", "processor", "ram"]

    # Test error case - non-existent column
    df = TinyDataFrame(sample_data)  # Reset
    with pytest.raises(KeyError):
        df.rename({"nonexistent": "new_name"})

    # Test chaining operations
    df = TinyDataFrame(sample_data)  # Reset
    result = df.rename({"cpu": "processor"})[["timestamp", "processor"]][3:6][
        "processor"
    ]
    assert result == [52.4, 78.2, 92.7]


def test_stats(sample_data):
    """Test the stats method"""
    df = TinyDataFrame(sample_data)
    stats = df.stats([StatSpec(column="cpu", agg=mean, round=2)])
    assert stats["cpu"]["mean"] == 46.16
    stats = df.stats(
        [
            StatSpec(column="cpu", agg=mean, round=0),
            StatSpec("memory", max),
            StatSpec("memory", len, agg_name="count"),
        ]
    )
    assert stats["cpu"]["mean"] == 46
    assert stats["memory"]["max"] == 4800
    assert stats["memory"]["count"] == 12


# ---------------------------------------------------------------------------
# CSV structure: read from HTTP URL
# ---------------------------------------------------------------------------


def test_read_csv_from_http_url():
    """_read_csv fetches and parses a CSV from an HTTP/HTTPS URL."""
    csv_bytes = b'"name","count","score"\n"Alice",10,9.5\n"Bob",3,7.25\n'

    mock_response = MagicMock()
    mock_response.read.return_value = csv_bytes
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("resource_tracker.tiny_data_frame.urlopen", return_value=mock_response):
        df = TinyDataFrame(csv_file_path="https://example.com/data.csv")

    assert df.columns == ["name", "count", "score"]
    assert df["name"][0] == "Alice"
    assert df["count"][0] == 10          # must be int, not float
    assert isinstance(df["count"][0], int)
    assert df["score"][0] == 9.5
    assert isinstance(df["score"][0], float)
    assert len(df) == 2


# ---------------------------------------------------------------------------
# CSV structure: corrupt file (extra fields create None key)
# ---------------------------------------------------------------------------


def test_read_csv_corrupt_extra_fields(tmp_path):
    """Rows with more fields than the header produce a None key → RuntimeError."""
    csv_path = tmp_path / "corrupt.csv"
    # Third field on the data row has no matching header → DictReader uses None as key
    csv_path.write_text('"a","b"\n"x","y","z"\n')

    with pytest.raises(RuntimeError):
        TinyDataFrame(csv_file_path=str(csv_path))


# ---------------------------------------------------------------------------
# CSV structure: retry on transient read failure
# ---------------------------------------------------------------------------


def test_read_csv_retries_on_dict_reader_failure(tmp_path):
    """_read_csv retries when DictReader raises, succeeds on a later attempt."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text('"col"\n"hello"\n"world"\n')

    real_dict_reader = DictReader
    call_count = [0]

    def flaky_dict_reader(source, *args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise OSError("File temporarily locked")
        return real_dict_reader(source, *args, **kwargs)

    with patch("resource_tracker.tiny_data_frame.DictReader", side_effect=flaky_dict_reader):
        with patch("resource_tracker.tiny_data_frame.sleep"):
            df = TinyDataFrame(csv_file_path=str(csv_path), retries=2, retry_delay=0.01)

    assert call_count[0] == 2
    assert df["col"] == ["hello", "world"]


def test_read_csv_raises_after_all_retries_exhausted():
    """RuntimeError is raised when every retry attempt fails."""
    with pytest.raises(RuntimeError, match="Failed to read CSV file after"):
        TinyDataFrame(
            csv_file_path="/nonexistent/does_not_exist.csv",
            retries=2,
            retry_delay=0,
        )


# ---------------------------------------------------------------------------
# CSV structure: various numeric types round-trip
# ---------------------------------------------------------------------------


def test_csv_round_trip_preserves_int_type(tmp_path):
    """Integers survive write→read as int, not float."""
    df = TinyDataFrame({"pid": [1001, 1002, 1003], "count": [5, 10, 15]})
    csv_path = tmp_path / "ints.csv"
    df.to_csv(str(csv_path))
    loaded = TinyDataFrame(csv_file_path=str(csv_path))

    assert loaded["pid"] == [1001, 1002, 1003]
    assert all(isinstance(v, int) for v in loaded["pid"])
    assert all(isinstance(v, int) for v in loaded["count"])


def test_csv_round_trip_preserves_float_type(tmp_path):
    """Floats survive write→read as float (not collapsed to int even if whole-number)."""
    df = TinyDataFrame({"cpu": [1.0, 2.5, 3.14]})
    csv_path = tmp_path / "floats.csv"
    df.to_csv(str(csv_path))
    loaded = TinyDataFrame(csv_file_path=str(csv_path))

    assert loaded["cpu"] == [1.0, 2.5, 3.14]
    assert all(isinstance(v, float) for v in loaded["cpu"])


def test_csv_round_trip_preserves_negative_numbers(tmp_path):
    """Negative ints and floats survive write→read with correct sign and type."""
    df = TinyDataFrame({"delta": [-10, -3, 0, 7], "rate": [-1.5, 0.0, 2.5, -3.14]})
    csv_path = tmp_path / "neg.csv"
    df.to_csv(str(csv_path))
    loaded = TinyDataFrame(csv_file_path=str(csv_path))

    assert loaded["delta"] == [-10, -3, 0, 7]
    assert all(isinstance(v, int) for v in loaded["delta"])
    assert loaded["rate"] == [-1.5, 0.0, 2.5, -3.14]
    assert all(isinstance(v, float) for v in loaded["rate"])


def test_csv_round_trip_with_mixed_types_and_strings(tmp_path):
    """Mixed string/int/float columns all survive a full write→read round-trip."""
    df = TinyDataFrame(
        {
            "label": ["foo", "bar", "baz"],
            "n": [42, 0, -7],
            "x": [3.14, -0.5, 1.0],
        }
    )
    csv_path = tmp_path / "mixed.csv"
    df.to_csv(str(csv_path))
    loaded = TinyDataFrame(csv_file_path=str(csv_path))

    assert loaded["label"] == ["foo", "bar", "baz"]
    assert all(isinstance(v, str) for v in loaded["label"])
    assert loaded["n"] == [42, 0, -7]
    assert all(isinstance(v, int) for v in loaded["n"])
    assert loaded["x"] == [3.14, -0.5, 1.0]
    assert all(isinstance(v, float) for v in loaded["x"])


def test_csv_round_trip_strings_with_commas_and_quotes(tmp_path):
    """String values that contain commas or quotes are quoted and round-trip correctly."""
    df = TinyDataFrame({"desc": ['hello, world', 'say "hi"', "plain"]})
    csv_path = tmp_path / "special.csv"
    df.to_csv(str(csv_path))
    loaded = TinyDataFrame(csv_file_path=str(csv_path))

    assert loaded["desc"] == ['hello, world', 'say "hi"', "plain"]


# ---------------------------------------------------------------------------
# __iter__ and to_dict
# ---------------------------------------------------------------------------


def test_iter(sample_data):
    """Iterating over TinyDataFrame yields row dicts."""
    df = TinyDataFrame(sample_data)
    rows = list(df)

    assert len(rows) == 12
    assert rows[0] == {"timestamp": 1737676800, "cpu": 15.5, "memory": 2500}
    assert rows[5]["cpu"] == 92.7


def test_to_dict(sample_data):
    """to_dict returns a list of row dictionaries."""
    df = TinyDataFrame(sample_data)
    result = df.to_dict()

    assert isinstance(result, list)
    assert len(result) == 12
    assert result[5]["cpu"] == 92.7
    assert result[0] == {"timestamp": 1737676800, "cpu": 15.5, "memory": 2500}


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------


def test_repr(sample_data):
    """__repr__ returns the expected one-liner summary."""
    df = TinyDataFrame(sample_data)
    r = repr(df)

    assert "TinyDataFrame with 12 rows and 3 columns" in r
    assert "First row as a dict" in r
    assert "timestamp" in r


# ---------------------------------------------------------------------------
# __str__ with string-valued column (left-align branch)
# ---------------------------------------------------------------------------


def test_str_with_string_column():
    """__str__ left-aligns string cells (exercises the except ValueError branch)."""
    df = TinyDataFrame({"name": ["Alice", "Bob"], "score": [95.5, 87.3]})
    output = str(df)

    assert "Alice" in output
    assert "Bob" in output
    assert "score" in output
    # Numbers should be right-aligned; verify both rows appear
    lines = output.split("\n")
    data_lines = [l for l in lines if "Alice" in l or "Bob" in l]
    assert len(data_lines) == 2


# ---------------------------------------------------------------------------
# to_csv: no-path (returns string) and quote_strings=False
# ---------------------------------------------------------------------------


def test_to_csv_returns_string(sample_data):
    """to_csv() without a path returns the CSV content as a string."""
    df = TinyDataFrame(sample_data)
    csv_str = df.to_csv()  # no path

    assert isinstance(csv_str, str)
    assert '"timestamp"' in csv_str   # header string-quoted
    assert "15.5" in csv_str
    assert "92.7" in csv_str


def test_to_csv_no_quoting(sample_data):
    """to_csv(quote_strings=False) uses QUOTE_MINIMAL (no forced string quotes)."""
    df = TinyDataFrame(sample_data)
    csv_str = df.to_csv(quote_strings=False)

    assert isinstance(csv_str, str)
    # QUOTE_MINIMAL: plain column names without surrounding double-quotes
    assert "timestamp" in csv_str
    assert '"timestamp"' not in csv_str


# ---------------------------------------------------------------------------
# stats: error handling when agg function raises
# ---------------------------------------------------------------------------


def test_stats_with_failing_agg(sample_data):
    """stats() logs and skips a spec whose agg function raises; other specs still work."""
    df = TinyDataFrame(sample_data)

    def bad_agg(col):
        raise RuntimeError("intentional failure")

    result = df.stats(
        [
            StatSpec(column="cpu", agg=bad_agg, agg_name="bad"),
            StatSpec(column="memory", agg=max),
        ]
    )

    # bad_agg result should be absent (error was caught and logged)
    assert "bad" not in result.get("cpu", {})
    # the valid spec should still produce a result
    assert result["memory"]["max"] == 4800

