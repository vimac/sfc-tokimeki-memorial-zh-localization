# Tokimeki Memorial (SFC JP Rev 1) — control-code widths and semantics

Recovered by disassembling every handler reachable from the text dispatcher
(`$80:CA6D`), not copied from the archived handoffs in `docs/history/`.

## Dispatch path (`$80:CAEB`, file `0x4AEB`)

```
80CAEB: A0 01 00   LDY #$0001        ; Y = 1, used by every operand read below
80CAEE: C9 38 00   CMP #$0038
80CAF1: 30 03      BMI $CAFE
80CAF3: 4C 67 CD   JMP $CD67         ; $38..$3F -> handler $CD67 (indexed by code-$38)
80CAFE: C9 30 00   CMP #$0030
80CAFB: 4C 8C CD   JMP $CD8C         ; $30..$37 -> handler $CD8C (indexed by (code-$30)*32)
80CAFE: DA 0A AA   PHX : ASL : TAX   ; $00..$2F -> table
80CB01: BF 0B CB 80 LDA $80CB0B,X    ; handler address, little-endian
80CB06: 85 00 / 6C 00 00  STA $00 : JMP ($0000)
```

**The table is 47 entries (`$00`-`$2E`), at file `0x4B0B`.** `$2F` and above are *not*
out-of-range: `$30..$37` and `$38..$3F` each have a single indexed handler, so a block that
uses them (block 8 uses `$39` x24, `$3A` x8, `$3B` x29, `$3C`/`$3D`/`$3F`) is legitimate.

Advance is read off the handler's tail: the cursor-advance chain is five stacked
`INC $B4` at `$CA9A/$CA9C/$CA9E/$CAA0/$CAA2`, so `JMP $CAA2`=1 byte, `$CAA0`=2, `$CA9E`=3,
`$CA9C`=4, `$CA9A`=5.

## Width table (bytes consumed, code byte included)

| code | handler | width | operand reads | what it does |
|---|---|---|---|---|
| `$00 xx` | `$CB69` | 2 | 0 | `LDA #$0000 : JSL $D23D` = draw the blank cell; the operand is ignored |
| `$01 xx` | `$CB73` | 2 | 2 | **computed forward jump** (see below) |
| `$02 xx` | `$CB8B` | 2 | 0 | call: pushes `cursor+3` then `STA $B4` from the operand -> jump to a 1-byte address in the same bank |
| `$03 xx yy` | `$CB9C` | 4 | 2 | reads a 16-bit WRAM word selected by 2 operands, `JSL $CFC5`, advance 4 |
| `$04 xx` | `$CBD0` | 2 | 1 | `STA $0A2C` = **set the font style flags** (bit0 planes, bit1 outline, bit4 kana, bit5 bold) |
| `$05` | `$CBDB` | 1 | 0 | copies the 16-px cell at `$7E:9FFE` <-> `$7EA000` around `$0A26`, `INC $0A26` |
| `$06` | `$CBF9` | 1 | 0 | `LDA $0A26 : STA $0A28` = save the line-start cell |
| `$07 xx` | `$CC02` | 2 | 1 | `$0A26 += operand` = move the cell cursor right |
| `$08 xx` | `$CC11` | 2 | 1 | `$0A26 = $0A28 + operand` = absolute cell on the current line |
| `$09 xx yy` | `$CC20` | 3 | 1 (16-bit) | `$0A26 = $0A28 = word` = **absolute tile cursor**, advance 3 (NOT a space) |
| `$0A` | `$CC2B` | 1 | 0 | macro return: `PLA : BNE : RTL / STA $B4 : PLA : STA $B6` |
| `$0B` | `$CC37` | 1 | 0 | newline: `$0A26 = $0A28 + $40` |
| `$0C` | `$CC47` | 1 | 0 | pop one pending sub-parse level (`PLA : PLA : $0A`-like) |
| `$0D` | `$CC4E` | 1 | 0 | tile-counter arithmetic from `$0A22` |
| `$0E` | `$CCB5` | 1 | 0 | big handler (178 B), `JSR` twice then advance 1 |
| `$0F p0 p1 p2 p3` | `$CBB0` | **5** | 2 | reads 2 operands + a WRAM word, `JSL $CFC5`, advance 5 |
| `$10` | `$CDC9` | 1 | 0 | `LDA #$0010 : STA $0A2C` = switch to the kana-variant ("handwritten") font |
| `$11` | `$CDD2` | 1 | 0 | `STZ $0A2C` = back to the normal font |
| `$12` / `$13` / `$16` | `$CDD8`/`$CDE8`/`$CDF8` | 1 | 0 | push the cursor and re-dispatch on WRAM `$0E00`/`$0E08`/`$0E10` (player name buffers) |
| `$14` | `$CE7D` | 1 | 0 | box/line geometry: `JSR $CF36`, then a loop that pushes `$0C` and `JSL $81E86C` |
| `$15` | `$CE9A` | 1 | 0 | `JSL $80D0B8 : LDA #$0008 : JSL $80C563` |
| `$17` | `$CE08` | 1 | 0 | push cursor, re-dispatch on `$83:8318` |
| `$18` | `$CEA8` | 1 | 0 | `JSL $80D061`-family + `INC $17DE` |
| `$19` | `$CE7D` | 1 | 0 | **alias of `$14`** (same handler address in the table) |
| `$1A`-`$1F` | `$CEB8`.. | 1 | 0 | chain: `LDA #$0000..#$0005` then `BRA` into one shared tail; `$1F` additionally reads `$00C4` |
| `$20` | `$CE68` | 1 | 0 | compares `$BC` with `$000A`, conditional `JSL $80D0F3` |
| `$21` `$22` `$23` | `$CE5F` `$CEFA` `$CF03` | 1 | 0 | set / clear the WRAM flag at `$17DC` / `$17DE` |
| `$24` `$25` `$26` | `$CF09` `$CF2C` `$CF31` | 1 | 0 | one routine with `Y = $0C / $08 / $04` (the `BRA` chaining proves it) |
| `$27` | `$CE40` | 1 | 0 | wait loop on `$17DC` |
| `$28 xx` | `$CE48` | 2 | 1 | `STZ $17DE`, operand scaled `*4`, `PHA : JSL $81E86C` = pass a parameter to the text engine |
| `$29` | `$CE8F` | 1 | 0 | `JSR $CF36 : INC $0A26 : LDA #$000C : BRA $CE7D` = open a box then behave like `$14` |
| `$2A`-`$2D` | `$CC47` | 1 | 0 | **aliases of `$0C`** |
| `$2E` | `$CAA2` | 1 | 0 | the handler *is* the advance stub -> a literal no-op pad byte |
| `$30`-`$37 xx` | `$CD8C` | 2 | 0 | reads the operand, indexes by `(code-$30)*32` into a table |
| `$38`-`$3F` | `$CD67` | 1 | 0 | reads the operand, `SEC : SBC #$0038 : JSL $CD77` = 8 variants of one indexed op |

## `$01`, the code that garbles a naive parse

```
80CB73: B7 B4   LDA [$B4],Y   ; operand = the byte after the code
80CB75: A8      TAY
80CB76: B9 00 00 LDA $0000,Y  ; -> a WRAM 16-bit word (a runtime selector)
80CB79: 18 69 03 00 CLC : ADC #$0003
80CB7D: A8      TAY
80CB7E: B7 B4   LDA [$B4],Y   ; -> a byte from an in-stream jump table
80CB83: 18 65 B4 CLC : ADC $B4 ; $B4 is still the $01 byte itself
80CB86: 85 B4   STA $B4
80CB88: 4C 6D CA JMP $CA6D
```

`new cursor = c + byte_at(c + word@($0000+operand) + 3)` — the jump distance is taken
relative to the `$01` byte, so the operand selects which in-stream distance table to use and
the runtime word selects which entry. In block 8 the operand is `$A0` 160 times and `$00` 50
times, i.e. the WRAM selector lives at `$7E:00A0/$7E:0000`. A linear walk therefore keeps
reading, but the *bytes after* a `$01` are partly distance-table, not text.

## Consequences for patching

1. Any block that executes `$00/$01/$02/$03/$04/$07/$08/$09/$0F/$28/$30..$37` must be walked
   with these widths. Reading them as 1 byte desynchronises every later atom: the symptom is
   correct words with phantom syllables injected (`（最近、女子生徒じゃないか？）` ->
   `（最よ近、女演奏生じゃないか徒？」`).
2. Because `$01` jumps to `c + <distance byte>`, translating a block that uses it can only be
   done with **every atom offset preserved** (block-144-style fixed spans), or by recomputing
   the distance bytes as well. Preserving spans is the safe default.
3. `tools/block_boxes.py` implements the widths and splits a block into its TERM-delimited
   segments; `docs/research/block8_boxes.json` + `block8_jp.txt` are its block-8 output.
