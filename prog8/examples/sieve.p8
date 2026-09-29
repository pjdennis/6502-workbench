; Sieve of Eratosthenes -- a non-trivial Prog8 program demonstrating
; arrays, nested loops, multiplication, comparison, when, address-of.
;
; Marks composites in `sieve[]` up to N-1, then prints all primes
; below N in hex. With N=64 the output is:
;   02030507 0B0D1113 171D1F25 292B2F35 3B3D
; (the primes 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
; 53, 59, 61 -- everything below 64 that's prime).

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

const ubyte N = 64
ubyte[64] sieve

  sub start() {
    lcd.clear()

    ; Initialize: sieve[0..N-1] = 0 (composite-flag, 0 = prime so far).
    ubyte i
    for i in 0 to N - 1 {
        sieve[i] = 0
    }
    ; 0 and 1 are not primes -- mark them composite.
    sieve[0] = 1
    sieve[1] = 1

    ; Cross out multiples. For i from 2, while i*i < N, mark j=i*i,
    ; i*i+i, ... as composite.
    for i in 2 to 7 {                 ; 7 = floor(sqrt(63))
        if sieve[i] == 0 {
            ubyte j
            j = i * i
            while j < N {
                sieve[j] = 1
                j = j + i
            }
        }
    }

    ; Print survivors as hex bytes, with a space every 4 numbers.
    ubyte found
    found = 0
    for i in 2 to N - 1 {
        if sieve[i] == 0 {
            txt.print_ub(i)
            found = found + 1
            when found & $03 {
                0 -> { txt.print(" ") }
                else -> { }
            }
        }
    }
  }
}
