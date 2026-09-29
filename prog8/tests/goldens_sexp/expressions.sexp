;;; '42'
(int 42)

;;; '$ff'
(int 255)

;;; '%1010'
(int 10)

;;; "'A'"
(int 65)

;;; "'\\n'"
(int 10)

;;; '"hello"'
(str "hello")

;;; 'true'
(bool true)

;;; 'false'
(bool false)

;;; 'foo'
(id foo)

;;; 'a.b'
(id a.b)

;;; 'a.b.c'
(id a.b.c)

;;; '-x'
(u-
  (id x))

;;; '- -x'
(u-
  (u-
    (id x)))

;;; '~x'
(~
  (id x))

;;; 'not flag'
(not
  (id flag))

;;; 'not a'
(not
  (id a))

;;; '&buf'
(addr buf)

;;; '&counter'
(addr counter)

;;; '@(ptr)'
(mem
  (id ptr))

;;; '@(ptr + 1)'
(mem
  (+
    (id ptr)
    (int 1)))

;;; '@($8000 + i)'
(mem
  (+
    (int 32768)
    (id i)))

;;; 'a + b'
(+
  (id a)
  (id b))

;;; 'a - b - c'
(-
  (-
    (id a)
    (id b))
  (id c))

;;; 'a + b * c'
(+
  (id a)
  (*
    (id b)
    (id c)))

;;; 'a * b + c'
(+
  (*
    (id a)
    (id b))
  (id c))

;;; 'a + b & c'
(&
  (+
    (id a)
    (id b))
  (id c))

;;; 'a | b & c'
(|
  (id a)
  (&
    (id b)
    (id c)))

;;; 'a ^ b | c'
(|
  (^
    (id a)
    (id b))
  (id c))

;;; 'a << b + c'
(<<
  (id a)
  (+
    (id b)
    (id c)))

;;; 'a >> b'
(>>
  (id a)
  (id b))

;;; 'a < b == c'
(==
  (<
    (id a)
    (id b))
  (id c))

;;; 'a <= b'
(<=
  (id a)
  (id b))

;;; 'a > b >= c'
(>=
  (>
    (id a)
    (id b))
  (id c))

;;; 'a != b'
(!=
  (id a)
  (id b))

;;; 'a and b or c'
(or
  (and
    (id a)
    (id b))
  (id c))

;;; 'a or b and c'
(or
  (id a)
  (and
    (id b)
    (id c)))

;;; 'a xor b'
(xor
  (id a)
  (id b))

;;; 'a and b and c'
(and
  (and
    (id a)
    (id b))
  (id c))

;;; '-a * b'
(*
  (u-
    (id a))
  (id b))

;;; 'a * -b'
(*
  (id a)
  (u-
    (id b)))

;;; 'not a and b'
(and
  (not
    (id a))
  (id b))

;;; '-a + -b'
(+
  (u-
    (id a))
  (u-
    (id b)))

;;; '~a & ~b'
(&
  (~
    (id a))
  (~
    (id b)))

;;; '(a)'
(id a)

;;; '(a + b)'
(+
  (id a)
  (id b))

;;; '(a + b) * c'
(*
  (+
    (id a)
    (id b))
  (id c))

;;; 'a * (b + c)'
(*
  (id a)
  (+
    (id b)
    (id c)))

;;; '((a + b) * (c - d)) | e'
(|
  (*
    (+
      (id a)
      (id b))
    (-
      (id c)
      (id d)))
  (id e))

;;; '(((x)))'
(id x)

;;; 'f()'
(call f)

;;; 'f(a)'
(call f
  (id a))

;;; 'f(a, b)'
(call f
  (id a)
  (id b))

;;; 'f(a, b, c)'
(call f
  (id a)
  (id b)
  (id c))

;;; 'foo.bar(1, $20, "x")'
(call foo.bar
  (int 1)
  (int 32)
  (str "x"))

;;; 'peek($8000)'
(call peek
  (int 32768))

;;; 'mkword(a, b)'
(call mkword
  (id a)
  (id b))

;;; 'f(a + b, c * d)'
(call f
  (+
    (id a)
    (id b))
  (*
    (id c)
    (id d)))

;;; 'f(g(h(x)))'
(call f
  (call g
    (call h
      (id x))))

;;; 'outer(inner(a), b)'
(call outer
  (call inner
    (id a))
  (id b))

;;; 'f(a) + g(b)'
(+
  (call f
    (id a))
  (call g
    (id b)))

;;; 'lsb(addr) | msb(addr)'
(|
  (call lsb
    (id addr))
  (call msb
    (id addr)))

;;; 'arr[0]'
(idx
  (id arr)
  (int 0))

;;; 'arr[i]'
(idx
  (id arr)
  (id i))

;;; 'arr[i + 1]'
(idx
  (id arr)
  (+
    (id i)
    (int 1)))

;;; 'tokens[idx].kind'
(idx
  (id tokens)
  (id idx)
  .kind)

;;; 'a.b[c]'
(idx
  (id a.b)
  (id c))

;;; 'a.b[c].d'
(idx
  (id a.b)
  (id c)
  .d)

;;; 'arr[f(i)]'
(idx
  (id arr)
  (call f
    (id i)))

;;; 'arr[i] + arr[j]'
(+
  (idx
    (id arr)
    (id i))
  (idx
    (id arr)
    (id j)))

;;; 'a + b * c - d'
(-
  (+
    (id a)
    (*
      (id b)
      (id c)))
  (id d))

;;; 'f(x) + arr[i] * 2 - @(p)'
(-
  (+
    (call f
      (id x))
    (*
      (idx
        (id arr)
        (id i))
      (int 2)))
  (mem
    (id p)))

;;; 'not (a == b) and (c < d or e >= f)'
(and
  (not
    (==
      (id a)
      (id b)))
  (or
    (<
      (id c)
      (id d))
    (>=
      (id e)
      (id f))))

;;; '(lsb(x) << 8) | msb(y)'
(|
  (<<
    (call lsb
      (id x))
    (int 8))
  (call msb
    (id y)))

;;; '&buf + i * 2'
(+
  (addr buf)
  (*
    (id i)
    (int 2)))

