import pytest

from resource_tracker import TinyDataFrame


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
    assert isinstance(loaded_df["int_col"][0], (int, float))  # CSV might load as float
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
