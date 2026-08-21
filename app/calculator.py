# app/calculator.py

def add(a: int, b: int) -> int:
    """Return the sum of two integers.

    The original implementation mistakenly performed subtraction, which caused
    the `test_add` unit test to fail. This function now correctly adds the two
    arguments and returns the result.
    """
    return a + b

def divide(a: int, b: int) -> float:
    """Return the division of ``a`` by ``b`` as a float.

    Raises:
        ValueError: If ``b`` is zero to avoid a ``ZeroDivisionError``.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
