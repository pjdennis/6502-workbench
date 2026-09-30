;;; '%output raw\n%launcher none\nmain {\n  sub start() {   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))))

;;; 'main {\n  sub start() { txt.print("hi")   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (exprstmt
          (call txt.print
            (str "hi")))))))

;;; '%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { x = 1 x += 2 x <<= 1   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte x))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (assign =
          (id x)
          (int 1))
        (assign +=
          (id x)
          (int 2))
        (assign <<=
          (id x)
          (int 1))))))

;;; '%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { if x == 0 { x = 1 }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte x))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (if
          (==
            (id x)
            (int 0))
          (block
            (assign =
              (id x)
              (int 1))))))))

;;; '%output raw\n%launcher none\nmain {\nubyte x\n  sub start() { if x == 0 { x = 1 } else { x = 2 }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte x))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (if
          (==
            (id x)
            (int 0))
          (block
            (assign =
              (id x)
              (int 1)))
          (block
            (assign =
              (id x)
              (int 2))))))))

;;; '%output raw\n%launcher none\nmain {\nubyte x\nubyte y\n  sub start() { if x != 0 { if y != 0 { x = 1 } else { x = 2 } } else { y = 3 }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte x)
    (var ubyte y))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (if
          (!=
            (id x)
            (int 0))
          (block
            (if
              (!=
                (id y)
                (int 0))
              (block
                (assign =
                  (id x)
                  (int 1)))
              (block
                (assign =
                  (id x)
                  (int 2)))))
          (block
            (assign =
              (id y)
              (int 3))))))))

;;; '%output raw\n%launcher none\nmain {\nubyte i\n  sub start() { while i < 10 { i = i + 1 }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte i))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (while
          (<
            (id i)
            (int 10))
          (block
            (assign =
              (id i)
              (+
                (id i)
                (int 1)))))))))

;;; 'main {\nubyte i\n  sub start() { for i in 0 to 7 { txt.print("x") }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte i))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (for i
          (int 0)
          (int 7)
          (block
            (exprstmt
              (call txt.print
                (str "x")))))))))

;;; '%output raw\n%launcher none\nmain {\n  sub start() { repeat { break }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (repeat
          (block
            (break)))))))

;;; 'main {\n  sub start() { repeat 5 { txt.print(".") }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (repeat
          (int 5)
          (block
            (exprstmt
              (call txt.print
                (str ".")))))))))

;;; 'main {\nubyte i\n  sub start() { for i in 0 to 3 { if i == 2 { continue } txt.print("y") }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte i))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (for i
          (int 0)
          (int 3)
          (block
            (if
              (==
                (id i)
                (int 2))
              (block
                (continue)))
            (exprstmt
              (call txt.print
                (str "y")))))))))

;;; 'main {\n  sub start() {   }\n  sub f(ubyte c) { when c { $61 -> { txt.print("a") } $62, $63 -> { txt.print("bc") } else -> { txt.print("?") } } }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))
    (subdef f sub void
      (params
        (param ubyte c))
      (block
        (when
          (id c)
          (choice
            (vals
              (int 97))
            (block
              (exprstmt
                (call txt.print
                  (str "a")))))
          (choice
            (vals
              (int 98)
              (int 99))
            (block
              (exprstmt
                (call txt.print
                  (str "bc")))))
          (choice
            (vals)
            (block
              (exprstmt
                (call txt.print
                  (str "?"))))))))))

;;; 'main {\nubyte x\n  sub start() {   }\n  sub g() { defer txt.print("3") defer txt.print("2") txt.print("body") }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte x))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))
    (subdef g sub void
      (params)
      (block
        (defer
          (exprstmt
            (call txt.print
              (str "3"))))
        (defer
          (exprstmt
            (call txt.print
              (str "2"))))
        (exprstmt
          (call txt.print
            (str "body")))))))

;;; 'main {\nubyte x\n  sub start() {   }\n  sub h() { defer if x != 0 { txt.print("z") } x = 1 }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte x))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))
    (subdef h sub void
      (params)
      (block
        (defer
          (if
            (!=
              (id x)
              (int 0))
            (block
              (exprstmt
                (call txt.print
                  (str "z"))))))
        (assign =
          (id x)
          (int 1))))))

;;; 'main {\n  sub start() {   }\n  sub r() -> ubyte { return 5 }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))
    (subdef r sub ubyte
      (params)
      (block
        (return
          (int 5))))))

;;; 'main {\n  sub start() {   }\n  sub r2() -> bool { return true }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))
    (subdef r2 sub bool
      (params)
      (block
        (return
          (bool true))))))

;;; 'main {\n  sub start() {   }\n  sub r3() { return }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block))
    (subdef r3 sub void
      (params)
      (block
        (return)))))

;;; '%output raw\n%launcher none\nmain {\n  sub start() { @($f001) = 7   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (assign =
          (mem
            (int 61441))
          (int 7))))))

;;; '%output raw\n%launcher none\nmain {\nubyte[4] arr\n  sub start() { arr[0] = 1 arr[1] = arr[0] + 2   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte[4] arr))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (assign =
          (idx
            (id arr)
            (int 0))
          (int 1))
        (assign =
          (idx
            (id arr)
            (int 1))
          (+
            (idx
              (id arr)
              (int 0))
            (int 2)))))))

;;; '%output raw\n%launcher none\nmain {\n  sub start() { %asm {{\nnop\n}}   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars)
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (asm "nop")))))

;;; '%output raw\n%launcher none\nmain {\nubyte a\nubyte b\n  sub start() { while a < 8 { for b in 0 to a { if b == 3 { break } } a = a + 1 }   }\n}'
(program
  (address $4000)
  (output raw)
  (target wendy2c)
  (imports)
  (vars
    (var ubyte a)
    (var ubyte b))
  (enums)
  (structs)
  (subs
    (subdef start main void
      (params)
      (block
        (while
          (<
            (id a)
            (int 8))
          (block
            (for b
              (int 0)
              (id a)
              (block
                (if
                  (==
                    (id b)
                    (int 3))
                  (block
                    (break)))))
            (assign =
              (id a)
              (+
                (id a)
                (int 1)))))))))

