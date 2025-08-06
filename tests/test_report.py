from resource_tracker.report import round_memory


def test_round_memory():
    assert round_memory(12) == 128
    assert round_memory(987) == 1024
    assert round_memory(1024) == 1024
    assert round_memory(1025) == 2048
