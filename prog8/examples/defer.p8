; Defer: LIFO cleanup before sub returns.

%address $4000
%output raw
%import txt
%import lcd
%launcher none
main {

sub work() {
    defer txt.print("3")           ; runs 3rd at exit
    defer txt.print("2")           ; runs 2nd at exit
    defer txt.print("1")           ; runs 1st at exit
    txt.print("body ")
}

  sub start() {
    lcd.clear()
    work()
    txt.print(" done")
  }
}
