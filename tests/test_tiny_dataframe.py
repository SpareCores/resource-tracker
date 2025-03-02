import pytest
import csv

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

    # Check data integrity - note that CSV values are loaded as strings
    assert df[columns[0]][0] == str(sample_data[columns[0]][0])
    assert df[columns[1]][5] == str(sample_data[columns[1]][5])
    assert df[columns[2]][11] == str(sample_data[columns[2]][11])
