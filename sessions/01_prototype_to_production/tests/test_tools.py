from research_assistant.tools import calculate


def test_calculate_arithmetic():
    assert calculate.invoke({"expression": "12000 / 2.5"}) == "4800.0"


def test_calculate_refuses_code():
    assert calculate.invoke({"expression": "__import__('os').getcwd()"}).startswith("error")
