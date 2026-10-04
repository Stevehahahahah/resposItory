1：

```python
def sum_even(n):
    total = 0
    for i in range(1, n + 1):
        if i % 2 == 0:
            total += i
    return total


n = int(input("Enter an integer n: "))

if n < -1:
    print("Invalid input")
else:
    print(f"Sum of even numbers: {sum_even(n)}")
```

2：

```python
def even_square(n):
    num = 1
    for row in range(n):
        values = []
        for col in range(n):
            if num % 2 == 0:
                values.append(str(num))
            else:
                values.append("*")
            num += 1
        print(" ".join(values))


even_square(3)
```

3：

```python
def hollow_diamond(n):
    center = n // 2
    for row in range(n):
        line = []
        for col in range(n):
            if abs(row - center) + abs(col - center) == center:
                line.append("*")
            else:
                line.append(".")
        print(" ".join(line))


while True:
    n = int(input("Enter an integer n (-1 to quit): "))

    if n == -1:
        break

    if n < 3 or n % 2 == 0:
        print("Invalid input")
    else:
        hollow_diamond(n)
```
