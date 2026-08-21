# app/test_calculator.py
import pytest
from app.calculator import add, divide

def test_add():
    assert add(2, 3) == 5

def test_divide():
    assert divide(10, 2) == 5.0
    with pytest.raises(ValueError):
        divide(10, 0)