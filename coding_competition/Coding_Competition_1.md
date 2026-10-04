# Coding Competition 1 解答

## 第一题：偶数求和（Sum of Even Numbers）

**题目要求：** 写一个函数 `sum_even(n)`，用循环算出 1 到 `n` 之间所有偶数的和。程序让用户输入 `n`：如果 `n` 小于 `-1`，输出 `Invalid input`；否则输出 `Sum of even numbers: 结果`。

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

**思路：** `sum_even` 用 `for` 循环从 1 走到 `n`，遇到偶数（`i % 2 == 0`）就加进 `total`，最后返回总和。主程序先检查输入是否小于 `-1`，再调用函数输出结果。

**运行示例：**

```
Enter an integer n: 10
Sum of even numbers: 30
```

> 注意：题目原文写的是"小于 `-1`"才算无效，代码是照原文写的，所以输入 `-1` 或 `0` 时会输出 `Sum of even numbers: 0`。如果题目本意是"小于 1"，把 `n < -1` 改成 `n < 1` 即可。

---

## 第二题：偶数方阵（Even Number Square）

**题目要求：** 写一个函数 `even_square(n)`，打印一个 `n × n` 的方阵，里面按顺序放 1 到 n²。偶数原样输出，奇数换成 `*`，每个值之间用空格隔开。

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

**思路：** 用 `num` 记录当前数字，从 1 开始。外层循环控制行，内层循环控制列，每格判断 `num` 是奇数还是偶数，放进这一行的列表，然后 `num` 加 1。一行填完后用 `" ".join()` 拼成带空格的字符串打印出来。

**运行示例（`n = 3`）：**

```
* 2 *
4 * 6
* 8 *
```

---

## 第三题：空心菱形（Hollow Diamond）

**题目要求：** 让用户输入 `n`，在 `n × n` 的方格里画一个空心菱形：边用 `*`，其他位置用 `.`，字符之间用空格隔开。程序一直让用户输入，直到输入 `-1` 才结束。只有大于等于 3 的奇数才能画出居中的菱形，否则输出 `Invalid input`。

```python
def hollow_diamond(n):
    center = n // 2
    for row in range(n):
        line = []
        for col in range(n):
            # A cell is on the diamond's edge when its distance from the center equals the radius
            if abs(row - center) + abs(col - center) == center:
                line.append("*")
            else:
                line.append(".")
        print(" ".join(line))


while True:
    try:
        n = int(input("Enter an integer n (-1 to quit): "))
    except ValueError:
        print("Invalid input")
        continue

    if n == -1:
        break

    if n < 3 or n % 2 == 0:
        print("Invalid input")
    else:
        hollow_diamond(n)
```

**思路：** 中心点是 `(n // 2, n // 2)`。一个格子到中心的横向距离加纵向距离（`abs(row - center) + abs(col - center)`）正好等于 `n // 2` 时，它就在菱形的边上，画 `*`，其余位置画 `.`。主程序用 `while True` 循环反复读取输入：输入 `-1` 时退出，偶数或小于 3 的数输出 `Invalid input`，其余情况画菱形。

另外加了一个题目没要求的处理：如果输入的不是整数（比如 `abc`），程序会输出 `Invalid input` 并继续让用户输入，而不是直接报错退出。

**运行示例：**

```
Enter an integer n (-1 to quit): 5
. . * . .
. * . * .
* . . . *
. * . * .
. . * . .
Enter an integer n (-1 to quit): 4
Invalid input
Enter an integer n (-1 to quit): -1
```
