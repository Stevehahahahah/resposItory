# Coding Competition 1

## 第一题：偶数求和

这题要写一个 `sum_even(n)` 函数，把 1 到 n 里面的偶数全部加起来。

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

我的想法是用 for 循环从 1 数到 n，每个数都用 `% 2` 看一下是不是偶数，是的话就加到 total 里面。题目说输入小于 -1 要输出 Invalid input，所以我先判断一下这个再去调用函数。

输入 10 的话结果是：

```
Sum of even numbers: 30
```

（2 + 4 + 6 + 8 + 10 = 30，对上了）

---

## 第二题：偶数方阵

这题要打印一个 n × n 的方阵，偶数照常打印，奇数换成 `*`。

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

我用了两个 for 循环，外面那个管行，里面那个管列。`num` 从 1 开始，每走一格就加 1。每一格先看 `num` 是奇数还是偶数，然后放进这一行的列表里。一行放满了就用 `" ".join()` 把它们用空格连起来打印。

n = 3 的时候结果是：

```
* 2 *
4 * 6
* 8 *
```

---

## 第三题：空心菱形

这题要在 n × n 的格子里画一个空心菱形，边是 `*`，其他地方是 `.`。程序要一直让用户输入，输入 -1 才停。

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

这题我一开始不知道怎么判断哪些格子是菱形的边，后来画了一下发现：中间那个格子是 `(n // 2, n // 2)`，菱形边上的每个格子，它离中间的上下距离加左右距离都刚好等于 `n // 2`。所以只要算 `abs(row - center) + abs(col - center)`，等于 center 就画 `*`，不等于就画 `.`。

然后用 `while True` 一直让用户输入，输入 -1 就 break 退出。题目说只有大于等于 3 的奇数才能画出来，所以偶数或者小于 3 的数就输出 Invalid input。

输入 5 的话结果是：

```
. . * . .
. * . * .
* . . . *
. * . * .
. . * . .
```
