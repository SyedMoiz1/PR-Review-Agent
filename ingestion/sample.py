#sample code file to test parser
class Animal:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    def speak(self) -> str:
        return f"{self.name} makes a sound"

    def get_age(self) -> int:
        return self.age


class Dog(Animal):
    def speak(self) -> str:
        return f"{self.name} says woof"


def add(a: int, b: int) -> int:
    return a + b


def greet(name: str) -> str:
    return f"Hello, {name}!"


def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
