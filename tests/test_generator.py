import pytest
from agent.test_generator import generate_edge_cases


def test_integer_pair():
    config = {
        "edge_cases": {
            "enabled": True,
            "generator": "integer_pair",
            "cases": ["both_zero", "mixed_signs"]
        }
    }

    tests = generate_edge_cases(config)

    assert len(tests) == 2
    assert tests[0]["expected_output"].strip() == "0"
    assert tests[1]["expected_output"].strip() == "10"


def test_sorting():
    config = {
        "edge_cases": {
            "enabled": True,
            "generator": "integer_array_sort",
            "cases": ["reverse_sorted", "duplicates"]
        }
    }

    tests = generate_edge_cases(config)

    assert len(tests) == 2
    assert tests[0]["expected_output"].strip() == "1 2 3 4 5"
    assert tests[1]["expected_output"].strip() == "1 2 2 4 4"


def test_searching():
    config = {
        "edge_cases": {
            "enabled": True,
            "generator": "linear_search",
            "cases": ["first_element", "not_found"]
        }
    }

    tests = generate_edge_cases(config)

    assert len(tests) == 2
    assert tests[0]["expected_output"].strip() == "0"
    assert tests[1]["expected_output"].strip() == "-1"


def test_string_reverse():
    config = {
        "edge_cases": {
            "enabled": True,
            "generator": "string_reverse",
            "cases": ["normal", "palindrome"]
        }
    }

    tests = generate_edge_cases(config)

    assert len(tests) == 2
    assert tests[0]["expected_output"].strip() == "olleh"
    assert tests[1]["expected_output"].strip() == "madam"


def test_disabled_generator_returns_empty_list():
    assert generate_edge_cases({
        "edge_cases": {"enabled": False}
    }) == []


def test_unsupported_generator_raises_error():
    config = {
        "edge_cases": {
            "enabled": True,
            "generator": "unknown_generator",
            "cases": []
        }
    }

    with pytest.raises(ValueError, match="Unsupported generator"):
        generate_edge_cases(config)


def test_invalid_enabled_type_raises_error():
    config = {
        "edge_cases": {
            "enabled": "true",
            "generator": "integer_pair",
            "cases": []
        }
    }

    with pytest.raises(ValueError, match="enabled"):
        generate_edge_cases(config)


def test_invalid_seed_raises_error():
    config = {
        "edge_cases": {
            "enabled": True,
            "generator": "integer_array_sort",
            "cases": ["random"],
            "seed": "42"
        }
    }

    with pytest.raises(ValueError, match="seed"):
        generate_edge_cases(config)