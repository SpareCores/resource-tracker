from resource_tracker.report import pretty_number, round_memory


def test_round_memory():
    assert round_memory(12) == 128
    assert round_memory(987) == 1024
    assert round_memory(1024) == 1024
    assert round_memory(1025) == 2048


def test_pretty_number():
    assert pretty_number(12) == "12"
    assert pretty_number(12.00012) == "12"
    assert pretty_number(12.28912) == "12.29"
    assert pretty_number(1234) == "1,234"
    assert pretty_number(1_234_567) == "1,234,567"
    assert pretty_number(1_234_567_890) == "1,234,567,890"
    assert pretty_number(1_234_567_890_123) == "1,234,567,890,123"
