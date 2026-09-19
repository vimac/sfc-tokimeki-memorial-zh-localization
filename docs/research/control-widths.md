# Control-code widths in the text dispatcher

Measured from the ROM itself with `tools/ctrl_advance.py` (it reads each of the
48 handler tails reached through the table at file `0x4B0B` and reports which
advance stub it jumps to).  The dispatcher at `$80:CA6D` is:

```
CA6A: PEA #$0000            ; a zero marker for the sub-parse stack
CA6D: LDA [$B4]             ; the byte at the cursor
CA72: CMP #$00F0 / BPL $CADE   ; $F0-$FF : 2-byte glyph,  idx = word - $F000
CA7A: CMP #$00E8 / BPL $CAC0   ; $E8-$EF : 2-byte sub-text macro (bank $C3)
CA7F: CMP #$00A0 / BPL $CAA6   ; $A0-$E7 : 1-byte phrase macro  (bank $B9)
CA84: CMP #$0040 / BMI $CAEB   ; $00-$3F : control
CA86:                ; else $40-$9F: 1-byte glyph from the BE16 table at $83:8000
```

The advance stubs are a chain of `INC $B4` at `$CA9A/$CA9C/$CA9E/$CAA0/$CAA2`,
so a handler's tail says how many stream bytes the code eats:
`JMP $CAA2` = 1, `JMP $CAA0` = 2, `JMP $CA9E` = 3, `BRA $CAA0` = 4.

## Codes that consume operand bytes

| code | handler | bytes eaten | what it does |
|------|---------|-------------|--------------|
| `$00` | `$CB69` | 2 | 1 operand byte |
| `$01` | `$CB73` | 2 | 1 operand byte |
| `$09` | `$CC20` | 3 | `LDA [$B4],Y` (Y=1) -> 16-bit operand stored to `$0A26/$0A28`: **set the tile write cursor** |
| `$28` | `$CE48` | 2 | operand = a frame-count delay, `(n+1)*4` |

Everything else below `$30` that the prologue actually executes eats one byte:
`$0A $0C $14 $18 $1C $24 $25 $26 $29 $2E`.  `$38-$3F` (`$CD67`) and `$30-$37`
(`$CD8C`) are the text-style/variable families and also need care, but block 144
executes none of them.

**Correction to earlier notes.**  `$09` is *not* a full-width space and `$0A` is
*not* a line break:

* `$0A` -> `$CC2B` is `PLA / BNE / RTL / STA $B4 / PLA / STA $B6 / JMP $CA6D`.
  Because the `$CA6A` `PEA #$0000` marker is what a top-level parse has on the
  stack, a top-level `$0A` pulls a zero word and `RTL`s (end of this parse),
  while a `$0A` inside a macro body pulls the cursor the call pushed at
  `$CAA6`/`$CAC6` and resumes after the call.  Its own advance is 1 byte.
* `$0B` -> `$CC37` is the newline (`$0A26 += $40`); `$0C` -> `$CC47` pops a
  pending sub-parse level and re-tests.
* `$2E` -> the table entry literally is `$CAA2`, i.e. a 1-byte no-op.

Block 144's executed control multiset (`tools/ctrl_widths.py`):
`$0A:5  $0C:84  $14:116  $18:1  $1C:1  $24:8  $25:20  $26:1  $29:2  $2E:7`
— 245 bytes, all one-byte.  So the Chinese re-layout cannot desync the cursor
through a control operand; counting raw bytes `$00-$3F` in the block instead
gives 60+ extra "controls" that are really the second byte of a `$F0/$F1/...`
glyph pair (`f0 09`, `f6 00`, `fd 01`), which is why an earlier pass suspected
operand bugs here.

## Font dispatch detail

`$80:D23D` (the shared glyph drawer for both bands) reads `$0A2C`:
bit 4 routes the index through the kana-variant redirect at `$80:D4BD`, bit 5
double-strikes the record, bit 1 selects another transform.  None of them touch
`$B4`, so drawing a glyph can never move the cursor.
