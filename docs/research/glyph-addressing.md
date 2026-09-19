# Tokimeki Memorial (SFC, JP Rev‑1) — text bytes → font glyph: exact algorithm

Target ROM: `REPO_ROOT/rom_original_japanese.sfc` (4 MiB, LoROM, 65816 native, 16‑bit A/X/Y).
Everything below was derived from the ROM's own machine code (byte‑level disassembly, no reliance on prior
notes) and verified by decoding real game text and rendering real glyph bitmaps.
The ROM was **not modified**.

Tooling used (created for this analysis):
* `tools/dis2.py` — 65816 disassembler with M/X flag tracking.
  `python3 tools/dis2.py <rom> <file_off_hex> <len_hex> [base_addr_hex]`
* `tools/glyphview.py` — implements the `$D490` formula and renders glyph slots as ASCII/PNG.
  `python3 tools/glyphview.py idx 0x546` / `blank` / `hist`

---

## 1. LoROM address map (verified)

`file = (bank - 0x80) * 0x8000 + (addr & 0x7FFF)`

Three absolute‑long operands inside the text routine prove it independently:

| operand in code | file offset | check |
|---|---|---|
| `LDA $838000,X` @ `$80:CA8C` | `0x18000` | (0x83‑0x80)*0x8000 = 0x18000 ✓ (contains a valid 96‑entry glyph table) |
| `LDA $B9CAA5,X` @ `$80:CAB2` | `0x1CCAA5` | (0xB9‑0x80)*0x8000 + 0x4AA5 = 0x1CCAA5 ✓ (valid pointer table) |
| `LDA $C396A8,X` @ `$80:CAD0` | `0x2196A8` | (0xC3‑0x80)*0x8000 + 0x16A8 = 0x2196A8 ✓ (valid pointer table) |

---

## 2. The text dispatcher — `$80:CA6D` (file `0x4A6D`)

Raw bytes `a7 b4 29 ff 00 c9 f0 00 10 67 c9 e8 00 10 44 c9 a0 00 10 25 c9 40 00 30 65 38 e9 40 00 0a`

```
80CA6D: A7 B4          LDA [$B4]        ; $B4/$B5/$B6 = 24-bit text cursor (bank at $B6)
80CA6F: 29 FF 00       AND #$00FF       ; current byte
80CA72: C9 F0 00       CMP #$00F0
80CA75: 10 67          BPL $CADE        ; $F0..$FF -> 2-byte glyph code
80CA77: C9 E8 00       CMP #$00E8
80CA7A: 10 44          BPL $CAC0        ; $E8..$EF -> 2-byte sub-table pointer
80CA7C: C9 A0 00       CMP #$00A0
80CA7F: 10 25          BPL $CAA6        ; $A0..$E7 -> phrase macro (1 byte)
80CA81: C9 40 00       CMP #$0040
80CA84: 30 65          BMI $CAEB        ; $00..$3F -> control codes
80CA86: 38             SEC              ; $40..$9F -> single-byte glyph shortcut
80CA87: E9 40 00       SBC #$0040
80CA8A: 0A             ASL
80CA8B: AA             TAX
80CA8C: BF 00 80 83    LDA $838000,X    ; table, 2 bytes per entry
80CA90: EB             XBA              ; entry is stored as a 2-byte TEXT CODE (big-endian)
80CA91: 29 FF 0F       AND #$0FFF       ; -> glyph index
80CA94: 22 3D D2 80    JSL $80D23D      ; draw glyph(index)
80CA98: 80 08          BRA $CAA2        ; advance cursor 1
80CA9A: E6 B4          INC $B4          ; (3 INCs; not reached by the paths above)
80CA9C: E6 B4          INC $B4
80CA9E: E6 B4          INC $B4
80CAA0: E6 B4          INC $B4          ; advance 2 (used by the 2-byte path)
80CAA2: E6 B4          INC $B4          ; advance 1 (used by the 1-byte path)
80CAA4: 80 C7          BRA $CA6D

; ---- phrase macro: replace the text cursor with a pointer into bank $B9 (call semantics) ----
80CAA6: E6 B4          INC $B4          ; step over the macro byte
80CAA8: D4 B6          PSHD $B6         ; push return cursor (bank)   [see note]
80CAAA: D4 B4          PSHD $B4         ; push return cursor (address)
80CAAC: 38             SEC
80CAAD: E9 A0 00       SBC #$00A0
80CAB0: 0A             ASL
80CAB1: AA             TAX
80CAB2: BF A5 CA B9    LDA $B9CAA5,X    ; phrase pointer table
80CAB6: 85 B4          STA $B4
80CAB8: A9 B9 00       LDA #$00B9
80CABB: 85 B6          STA $B6
80CABD: 4C 6D CA       JMP $CA6D

; ---- $E8..$EF: 2-byte code -> pointer into bank $C3 ----
80CAC0: A7 B4          LDA [$B4]
80CAC2: E6 B4          INC $B4
80CAC4: E6 B4          INC $B4          ; consume 2 text bytes
80CAC6: D4 B6          PSHD $B6
80CAC8: D4 B4          PSHD $B4
80CACA: EB             XBA              ; big-endian 16-bit value of the 2 bytes
80CACB: 29 FF 07       AND #$07FF       ; 2048-entry index
80CACE: 0A             ASL
80CACF: AA             TAX
80CAD0: BF A8 96 C3    LDA $C396A8,X
80CAD4: 85 B4          STA $B4
80CAD6: A9 C3 00       LDA #$00C3
80CAD9: 85 B6          STA $B6
80CADB: 4C 6D CA       JMP $CA6D

; ---- $F0..$FF: THE 2-BYTE KANJI PATH (pure arithmetic, no table) ----
80CADE: A7 B4          LDA [$B4]
80CAE0: EB             XBA              ; A = (b0<<8)|b1   (big-endian of the 2 text bytes)
80CAE1: 38             SEC
80CAE2: E9 00 F0       SBC #$F000       ; index = BE16 - 0xF000
80CAE5: 22 3D D2 80    JSL $80D23D      ; draw glyph(index)
80CAE9: 80 B5          BRA $CAA0        ; advance 2
```

Note on `D4 zp` (2 bytes): not a standard 65816 mnemonic. The reading "push the 16‑bit direct‑page word at
`zp`" is the only one that is consistent with all three of:
(a) the control‑code `$0A` handler, which pops exactly `$B4` then `$B6` in that LIFO order (§3.4);
(b) the paired `PLA : STA zp` epilogues used throughout this ROM (e.g. `$D23F`–`$D245`);
(c) linear‑sweep alignment — read as a 3‑byte `CPY abs`, the phrase block would end at `$CABF`, not at the
    observed next block start `$CAC0` (same test for the `$E8` block: `$CADC` vs the real `$CADE`).

### Byte bands (final, from the code above)

| text byte(s) | meaning | driving table |
|---|---|---|
| `$00`–`$3F` | control codes (`$00` = blank/space glyph, `$0A` = end‑of‑macro return) | `$80:CB0B` = file `0x4B0B`, 42 × 2 B little‑endian |
| `$40`–`$9F` | single‑byte glyph shortcut (96 slots) | `$83:8000` = file `0x18000`, 96 × 2 B big‑endian |
| `$A0`–`$E7` | phrase macro (text subroutine call) | `$B9:CAA5` = file `0x1CCAA5`, 72 × 2 B little‑endian |
| `$E8`–`$EF` | 2‑byte pointer into a secondary text bank | `$C3:96A8` = file `0x2196A8`, 2048 × 2 B little‑endian |
| `$F0`–`$FF` | **2‑byte glyph code — direct arithmetic, no table** | — |

**This refutes the prior claim that `$A0`–`$FC` are 2‑byte kanji codes.** `$A0`–`$E7` are phrase macros,
`$E8`–`$EF` are sub‑table selectors, and only `$F0`+ introduces a 2‑byte glyph code.

---

## 3. The tables, exactly

### 3.1 Single‑byte glyph table — file `0x18000` (`$83:8000`)
* 96 entries × 2 bytes = 192 bytes, `0x18000`–`0x180BF`.
* **Big‑endian**: `XBA` after the load, then `AND #$0FFF`. The stored value is literally a 2‑byte text code
  (`$F0xx`), so `index = BE16(entry) & $0FFF`.
* Entry for text byte `c` lives at `0x18000 + 2*(c - 0x40)`.
* Contents (index after masking, character identified via §7):
  `$40→035 「` `$41→036 」` `$42→029 （` `$43→02A ）` `$44→001 、` `$45→002 。` `$46→008 ？`
  `$47→023 …` `$48→024 ‥` `$49→14F ン` `$4A→11F ッ` `$4B→100 イ` `$4C→124 ト` `$4D→106 オ`
  `$4E→01B ー` `$4F→0FC ん` `$50→0AA ぁ` `$51→0AB あ` `$52→612 私` `$53→0AD` `$54→573 今`
  `$58→546 行` … `$82→9D0 当` `$83→605 思` `$86→CB2 来` `$87→A34 日` `$88→39E 気` `$89→4BF 見`
  `$8B→6BA 出` `$8C→773 人` `$8D→210 一` … `$9D→4D4 言` `$9F→0FB を`
  (punctuation, a katakana grab‑bag, the whole hiragana run `$4F`–`$9F`, and 13 high‑frequency kanji.)
* Those 13 kanji are 私(27‑68) 今(26‑03) 行(25‑52) 当(37‑86) 思(27‑55) 来(45‑72) 日(38‑92) 気(21‑04)
  見(24‑11) 出(29‑48) 人(31‑45) 一(16‑76) 言(24‑32) — every one lands on the correct JIS X0208 position
  under the §7 mapping. This is an **independent confirmation** of that mapping, from a table the earlier
  notes never mentioned.

### 3.2 Phrase macro table — file `0x1CCAA5` (`$B9:CAA5`)
* 72 entries × 2 bytes, **little‑endian 16‑bit offsets inside bank `$B9`** (bank is forced to `$B9`).
* Entry for text byte `c`: `0x1CCAA5 + 2*(c - 0xA0)`.
* Valid range: codes `$A0`–`$E6` → pointers `$CB33`…`$CCC6` (file `0x1CCB33`…`0x1CCCC6`). Code `$E7` holds
  `$02F0` (out of the `$8000`–`$FFFF` window) = unused.
* Phrase text is a normal stream in the same encoding; `$0A` separates the individual phrases.

### 3.3 Sub‑table — file `0x2196A8` (`$C3:96A8`)
* 2048 entries × 2 bytes (4096 bytes, `0x2196A8`–`0x21A6A7`), **little‑endian**, bank forced to `$C3`.
* Index = `BE16(E8xx..EFxx) & $07FF`, so the low byte selects within a 256‑entry page and `$E8`…`$EF`
  select pages 0…7. 1401 entries form a contiguous valid prefix, 1693 valid overall.

### 3.4 Control jump table — file `0x4B0B` (`$80:CB0B`)
* 42 entries × 2 bytes little‑endian for codes `$00`–`$29` (e.g. `$00→$CB69`, `$0A→$CC2B`, `$14→$CE7D`).
* The `$0A` handler is the proof of the macro call/return mechanism and of the `PSHD` reading:
```
80CC2B: 68             PLA              ; pop saved cursor address ($B4)
80CC2C: D0 01          BNE $CC2F        ; zero => sentinel => RTL (whole text routine exits)
80CC2E: 6B             RTL
80CC2F: 85 B4          STA $B4
80CC31: 68             PLA              ; pop saved cursor bank ($B6)
80CC32: 85 B6          STA $B6
80CC34: 4C 6D CA       JMP $CA6D        ; resume the caller's stream
```
  LIFO order matches `PSHD $B6 : PSHD $B4` exactly. `$00` (`$CB69`) is `LDA #$0000 : JSL $D23D :`
  `JMP $CAA0` = draw the blank glyph (space).

### 3.5 Kana‑variant index list — file `0x54E4` (`$80:D4E4`)
* 76 bytes terminated by `$00` at file `0x5530`; all values in `$AB`–`$FC` (hiragana range).
  `ab ad af b1 b3 b4 b6 b8 ba bc be c0 c2 c4 c6 c8 ca cd cf d1 d3 d4 d5 d6 d7 d8 db de e1 e4 e7 e8 e9 ea
   eb ed ef f1 f2 f3 f4 f5 f6 f8 fb fc f0 cc ec b5 b7 b9 bb bd bf c1 c3 c5 c7 c9 cb ce d0 d2 d9 dc df e2
   e5 da dd e0 e3 e6 f9 fa`
* Missing from `$AB`–`$FC`: `AC AE B0 B2 EE F7` (5 hiragana + 1 katakana‑range byte).

---

## 4. Glyph index → glyph record address — `$80:D490` (file `0x5490`)

```
80D490: A2 FD 00       LDX #$00FD       ; bank = $FD + page
80D493: A8             TAY              ; Y = index
80D494: 38             SEC
80D495: E9 92 04       SBC #$0492       ; while (index >= 0x492) index -= 0x492, bank++
80D498: 90 10          BCC $D4AA
80D49A: E8             INX
80D49B: A8             TAY
80D49C: E9 92 04       SBC #$0492       ; (no SEC: carry from the previous subtraction)
80D49F: 90 09          BCC $D4AA
80D4A1: E8             INX
80D4A2: A8             TAY
80D4A3: E9 92 04       SBC #$0492
80D4A6: 90 02          BCC $D4AA
80D4A8: E8             INX              ; 4th page -> bank $100 (invalid); unreachable for legal indices
80D4A9: A8             TAY
80D4AA: 86 02          STX $02          ; pointer bank
80D4AC: 98             TYA
80D4AD: 0A             ASL
80D4AE: 0A             ASL
80D4AF: 85 00          STA $00          ; t = y*4
80D4B1: 0A             ASL
80D4B2: 0A             ASL
80D4B3: 0A             ASL
80D4B4: 38             SEC
80D4B5: E5 00          SBC $00          ; y*32 - y*4  ==  y*28
80D4B7: 09 00 80       ORA #$8000       ; window base
80D4BA: 85 00          STA $00          ; pointer address
80D4BC: 60             RTS
```

So the routine builds a 24‑bit pointer at `$00/$01/$02`:

```
page   = index / 0x492                  (0,1,2)
y      = index % 0x492
bank   = $FD + page
addr   = $8000 + y*28
file   = (bank-$80)*0x8000 + (addr & 0x7FFF)
       = 0x3E8000 + page*0x8000 + (index % 0x492)*28
```

Constants proven: `0x492` (1170) appears three times as an immediate; `28` is built as `y*32 - y*4` and is
independently confirmed by the `$1C` copy loop in `$80:D265` (§5); `$FD` is the `LDX #$00FD` seed.

Addressable slot space: **3 pages × 1170 = 3510 slots, indices `$0000`–`$0DB5`.**
Index `$0DB6` and above would set bank `$100` and read from `$00:xxxx` — i.e. it is *not* addressable
without patching `$D490`.

---

## 5. The glyph record — `$80:D23D` (file `0x523D`)

```
80D23D: DA             PHX
80D23E: 5A             PHY
80D23F: D4 00          PSHD $00         ; save direct-page scratch ($00,$02,$04,$06)
80D241: D4 02          PSHD $02
80D243: D4 04          PSHD $04
80D245: D4 06          PSHD $06
80D247: 85 00          STA $00          ; A = glyph index
80D249: AD 2C 0A       LDA $0A2C        ; font style flags
80D24C: 89 10 00       BIT #$0010       ; bit4 = kana-variant ("handwritten") style
80D24F: F0 03          BEQ $D254
80D251: 20 BD D4       JSR  $D4BD       ; -> index remap (see §6)
80D254: A5 00          LDA $00
80D256: 20 90 D4       JSR  $D490       ; index -> 24-bit pointer at $00/$01/$02
80D259: 8B             PHB
80D25A: F4 7E 7E       PEA #$7E7E
80D25D: AB             PLB              ; DB = $7E (WRAM scratch follows)
80D25E: AB             PLB
80D25F: 9C 00 C1       STZ  $C100       ; row 0 of the 16-row cell = blank
80D262: A0 00 00       LDY  #$0000
80D265: B7 00          LDA  [$00],Y     ; read glyph word
80D267: 99 02 C1       STA  $C102,Y     ; -> row 1..14
80D26A: C8             INY
80D26B: C8             INY
80D26C: C0 1C 00       CPY  #$001C      ; *** exactly 28 bytes = 14 words ***
80D26F: D0 F4          BNE  $D265
80D271: 9C 1E C1       STZ  $C11E       ; row 15 = blank
80D274: AD 2C 0A       LDA  $0A2C
80D277: 89 20 00       BIT  #$0020      ; bit5 = bold -> thicken each row: w |= (w<<1)
80D27A: F0 18          BEQ  $D294
80D27C: A9 10 00       LDA  #$0010
...  80D284: LDA $C100,Y / ASL / ORA $C100,Y / STA $C100,Y  (16 words)
80D294: AD 2C 0A       LDA  $0A2C
80D297: 89 02 00       BIT  #$0002      ; bit1 = outline/shadow variant: JSL $80D5F2 + row merge
...
80D2F0: AD 2C 0A       LDA  $0A2C
80D2F3: 89 01 00       BIT  #$0001      ; bit0 = 1-plane variant (no plane-1 derivation)
80D2F6: F0 2C          BEQ  $D324
...  80D303: 16 rows: $C100,Y -> $C000,X ; $C002,X = 0 ; XBA on $C001,X ; X += 4
80D324: 64 06          STZ  $06         ; normal path: 1bpp -> 2bpp (4bpp planes 0/1)
80D326: A9 10 00       LDA  #$0010      ; 16 rows
80D329: 85 04          STA  $04
80D32B: A0 00 00       LDY  #$0000
80D32E: A2 00 00       LDX  #$0000
80D331: B9 00 C1       LDA  $C100,Y     ; row word
80D334: 9D 00 C0       STA  $C000,X     ; plane 0, 2 bytes (left 8 px, right 8 px)
80D337: 4A             LSR              ; build plane 1 = word | (word >> 1)
80D338: 48             PHA
80D339: 05 06          ORA  $06
80D33B: 9D 02 C0       STA  $C002,X     ; plane 1
80D33E: 68             PLA
80D33F: 85 06          STA  $06         ; carry bit for the next row
80D341: BD 01 C0       LDA  $C001,X
80D344: EB             XBA              ; byte-swap -> SFC tile order (MSB = leftmost pixel)
80D345: 9D 01 C0       STA  $C001,X
80D348: C8  C8         INY : INY
80D34A: 8A  18 69 04 00 AA   TXA : CLC : ADC #$0004 : TAX
80D350: C6 04          DEC  $04
80D352: D0 DD          BNE  $D331
80D354: AD 22 0A       LDA  $0A22       ; tile counter -> VRAM byte offset (*64)
80D357: 0A 0A 0A       ASL ASL ASL      ; 6 ASLs in total -> tile counter * 64
80D35D: AA             TAX
80D35E: A0 02 C0       LDY  #$C002      ; 4 x 16 bytes -> the 2x2 block of 8x8 tiles
80D361: 20 59 D4       JSR  $D459       ; (16 bytes each -> $C200,X, X += $10)
80D364: A0 00 C0       LDY  #$C000
80D367: 20 59 D4       JSR  $D459
80D36A: A0 22 C0       LDY  #$C022
80D36D: 20 59 D4       JSR  $D459
80D370: A0 20 C0       LDY  #$C020
80D373: 20 59 D4       JSR  $D459
80D376: AD 26 0A       LDA  $0A26       ; BG-map cell cursor
...  -> X = (cursor & $3FF)*8, Y = high byte
80D387: E2 20          SEP  #$20        ; 8-bit accumulator (bit5 = M)
80D389: A9 01          LDA  #$01
80D38B: 99 00 B2       STA  $B200,Y     ; "cell used" bookkeeping
80D38E: 99 01 B2       STA  $B201,Y
80D391: C2 20          REP  #$20
80D393: AD 22 0A       LDA  $0A22       ; first tile number of this glyph
80D397: 6D 24 0A       ADC  $0A24
80D39F: 6D 2A 0A       ADC  $0A2A
80D3A7: 9D 00 A0       STA  $A000,X     ; BG map: 2x2 tiles of 8x8 = one 16x16 cell
80D3AB: 9D 02 A0       STA  $A002,X     ; (tile number incremented between each store, `1A` = INC A)
80D3AF: 9D 40 A0       STA  $A040,X
80D3B3: 9D 42 A0       STA  $A042,X
80D3B6: EE 26 0A       INC  $0A26
80D3B9: EE 26 0A       INC  $0A26
80D3CB: AD 22 0A       LDA  $0A22
80D3D3: EE 22 0A       INC  $0A22       ; next tile index
```

### Record format (proved)
* **28 bytes = 14 × 16‑bit row words**, little‑endian in memory.
* Reading the pair as `w = (byte[1] << 8) | byte[0]` gives the pixel row with **bit15 = leftmost pixel**;
  only the **top 14 bits** are used (bits 1–0 are always 0 → the rightmost 2 pixels of the 16‑px cell are
  never drawn). So: `byte[1]` = left 8 pixels (MSB first), `byte[0]` bits 7…2 = pixels 8…13.
* The 14 rows are placed at **rows 1…14** of a 16‑row cell; rows 0 and 15 are forced blank
  (`STZ $C100`, `STZ $C11E`). Effective ink area = 14 × 14, drawn into a 16 × 16 cell.
* Runtime expansion: 1bpp → 2bpp (`plane1 = word | (word >> 1)`), then packed as a 2×2 block of 8×8 4bpp
  tiles (64 bytes) at `$7E:C000`, copied to the tile buffer `$7E:C200` by `$D459`.
* Style flags at `$7E:0A2C`: bit4 kana variant (`$D4BD` remap), bit5 bold, bit1 outline, bit0 plane mode.
  Tile counter `$0A22`, BG‑map cell cursor `$0A26`.

---

## 6. Optional runtime redirect — `$80:D4BD` (file `0x54BD`)

```
80D4BD: A5 00          LDA  $00          ; glyph index
80D4BF: C9 FD 00       CMP  #$00FD
80D4C2: 10 1F          BPL  $D4E3        ; index >= $FD -> unchanged
80D4C4: C9 AB 00       CMP  #$00AB
80D4C7: 30 1A          BMI  $D4E3        ; index <  $AB -> unchanged
80D4C9: A2 00 00       LDX  #$0000
80D4CC: BF E4 D4 80    LDA  $80D4E4,X    ; 76-entry list (§3.5)
80D4D0: 29 FF 00       AND  #$00FF
80D4D3: F0 0E          BEQ  $D4E3        ; $00 terminator
80D4D5: C5 00          CMP  $00
80D4D7: F0 03          BEQ  $D4DC
80D4D9: E8             INX
80D4DA: 80 F0          BRA  $D4CC
80D4DC: 8A             TXA
80D4DD: 18             CLC
80D4DE: 69 5A 0D       ADC  #$0D5A       ; new index = $0D5A + position
80D4E1: 85 00          STA  $00
80D4E3: 60             RTS
```

Active only when `$0A2C` bit 4 is set. It maps hiragana indices `$AB`–`$FC` (76 of the 83) onto indices
`$0D5A`–`$0DCA` (page 2, file `0x3FF5E8`…), i.e. a second, stylistically different kana set.

---

## 7. The glyph index space (calibrated by rendering real bitmaps)

| index range | count | contents |
|---|---|---|
| `$0000` | 1 | blank (space) — the only all‑zero slot in the font |
| `$0001`–`$005D` | 93 | **JIS X0208 ku 1, cells 2–94** (、。「」（）… ？ ！ ＿ etc.). Verified anchors: `$01`、 `$02`。 `$08`？ `$09`！ `$1B`ー `$24`‥ `$29`（ `$2A`） `$35`「 `$36`」 |
| `$005E`–`$006B` | 14 | **JIS ku 2, cells 1–14**: ◆□■△▲▽▼※〒→←↑↓〓 (rendered and confirmed) |
| `$006C`–`$0075` | 10 | ０–９ |
| `$0076`–`$008F` | 26 | Ａ–Ｚ |
| `$0090`–`$00A9` | 26 | ａ–ｚ |
| `$00AA`–`$00FC` | 83 | **hiragana = JIS ku 4 cells 1–83** (ぁ…ん, incl. ゐ`$F9` ゑ`$FA` を`$FB` ん`$FC`) |
| `$00FD`–`$0152` | 86 | **katakana = JIS ku 5 cells 1–86** (ァ`$FD` … ヶ`$152`) |
| `$0153`–`$015A` | 8 | narrow/half‑width extras: two 7‑px kana pairs, half‑width ー, italic `AB`, solid ◀ cursor |
| `$015B`–`$0179` | 31 | large proportional numerals **1–31** (calendar days) |
| `$017A` | 1 | solid heart |
| `$017B`–`$0182` | 8 | Greek lowercase ρ σ τ υ φ χ ψ ω |
| `$0183`–`$01A3` | 33 | Cyrillic uppercase А–Я |
| `$01A4`–`$01C4` | 33 | Cyrillic lowercase а–я |
| `$01C5`–`$0DB5` | 3057 | **kanji in JIS X0208 order, starting at ku 16 cell 1** |

Kanji formula:

```
index = 0x1C5 + ((ku - 16) * 94 + (cell - 1))          (JIS X0208 level 1 upwards)
ku    = 16 + (index - 0x1C5) / 94
cell  = 1  + (index - 0x1C5) % 94
EUC-JP bytes = (0xA0 + ku), (0xA0 + cell)
```

Anchor proofs (bitmap rendered, then read visually):

| index | JIS | rendered glyph |
|---|---|---|
| `$01C5` | 16‑01 | 亜 (first level‑1 kanji) |
| `$01C6` | 16‑02 | 唖 |
| `$01C7`–`$01CC` | 16‑03…08 | 娃 阿 哀 愛 挨 姶 |
| `$039C` | 21‑02 | 帰 |
| `$040D` | 22‑21 | 教 |
| `$04D4` | 24‑32 | 言 |
| `$0540`–`$0547` | 25‑46…53 | 肯 肱 腔 膏 航 荒 行 衡 |
| `$0628` | 27‑90 | 字 |
| `$0812` | 33‑16 | 前 |
| `$08EC` | 35‑46 | 知 |
| `$0A34` | 38‑92 | 日 |
| `$0C2A` | 44‑30 | 名 |
| `$0AF2` | 40‑94 | 美 |
| `$0DB5` | 48‑49 | 佰 (last slot; solid `$FFFF…` block) |

The last slot of each of `$0DAE`–`$0DB5` is a duplicate all‑`$FF` (solid) block — the only duplicated
bitmaps at the end of the range. Elsewhere, 24 slots duplicate an earlier bitmap, all of them Cyrillic
letters that are visually identical to a Latin letter (`$0183`А = `$0076`A, `$0185`В = `$0077`B,
`$0191`Н = `$007D`H, `$01B3`о = `$009E`o, …) — an additional, independent confirmation of the block map.

---

## 8. Worked examples, taken from actual game text

### 8.1 `F3 9C` → 帰 (page 0)
File `0x1CCB82` (bank `$B9`, `$B9:CB82`) is the start of phrase macro `$B0` — the phrase‑table entry at
`0x1CCAA5 + 2*(0xB0-0xA0) = 0x1CCAC5` holds `$CB82`; the bytes there are `… 0A F3 9C 99 F0 E7 66 96 55 0A …`
which the confirmed decoder renders as 「帰りましょう」 (`99` is the single‑byte shortcut → index `$0F3` = り).

```
text bytes            : F3 9C
$80:CADE  LDA [$B4]   : $009CF3   (little-endian read)
          XBA         : $F39C
          SEC/SBC F000: index = $039C
$80:D490  3 x SBC 0492: $039C < $0492 -> page 0, y = $039C, bank = $FD
          y*28        : $039C * 28 = 924 * 28 = 25872 = $6510
          ORA #$8000  : addr = $E510
pointer               : $FD:$E510
file offset           : (0xFD-0x80)*0x8000 + 0x6510 = $3EE510
```
Bitmap at `$3EE510` (28 bytes) rendered as 1bpp/14 columns = 帰 ✓ (see the ASCII art in §8.4).

### 8.2 `F5 46` → 行 (page 1)
```
index = $F546 - $F000 = $0546 ;  $0546 >= $0492 -> page 1, y = $0546-$0492 = $00B4 (180)
bank $FE, addr = $8000 + 180*28 = $8000 + 5040 = $93B0
file  = 0x3F0000 + $13B0 = $3F13B0        -> renders as 行 ✓
```
(`$58` in the single‑byte table also points at index `$0546`, i.e. text byte `$58` = 行.)

### 8.3 `FA F2` → 美 (page 2), from real text at file `0x1CCBB6`
```
index = $FAF2 - $F000 = $0AF2 ;  $0AF2 >= 2*$0492 -> page 2, y = $0AF2 - $0924 = $01CE (462)
bank $FF, addr = $8000 + 462*28 = $8000 + 12936 = $B288
file  = 0x3F8000 + $3288 = $3FB288        -> renders as 美 ✓   (JIS 40-94)
```
Context: `… FC 6F FA F2 …` = 「優美」, preceded at `0x1CCBA7` by `FB 69` = 聞 (index `$0B69`,
file `$3FBF8C`).

### 8.4 The bitmap at `$3EE510` decoded with the §5 format
```
   ________________
   _____#__________
   _____#_#######__
   _____#_______#__
   _____#__######__
   ___#_#_______#__
   ___#_#_#######__
   ___#_#__________
   __#__##########_
   _____##___#___#_
   _____#_#######__
   _____#_#__#__#__
   ____#__#__#__#__
   ____#__#__#_##__
   ___#______#_____
   ________________
```

---

## 9. Answers

**(a) 2‑byte code → glyph index.** Pure arithmetic, no table:
`index = ((b0 << 8) | b1) - 0xF000`.
The only runtime redirect is `$D4BD`, which (when `$0A2C` bit 4 is set) maps index `$AB`–`$FC` through the
76‑byte list at file `0x54E4` to `$0D5A + position`.

**(b) Index → file offset.**
`file = 0x3E8000 + (index / 0x492) * 0x8000 + (index % 0x492) * 28`, i.e. banks `$FD`, `$FE`, `$FF`,
1170 slots each, 28 bytes per slot. Record format: 14 little‑endian 16‑bit row words, MSB = leftmost pixel,
top 14 bits used, drawn at rows 1–14 of a 16×16 cell.

**(c) What to edit to redirect a code to another glyph slot.**
* 2‑byte codes: **no table exists** — the code *is* the index. Edit the two text bytes to
  `((0xF000 + new_index) >> 8) & $FF`, `(0xF000 + new_index) & $FF`. Legal new index range `$0000`–`$0DB5`
  (equivalently codes `$F0 00` … `$FD B5`).
* Single‑byte codes `$40`–`$9F`: edit the big‑endian pair at `0x18000 + 2*(code - 0x40)`; write
  `0xF000 | new_index` big‑endian (only the low 12 bits are read). 96 slots.
* Kana‑variant redirect: edit the 76‑byte list at file `0x54E4` (values `$AB`–`$FC`, `$00`‑terminated) —
  the target index is `$0D5A + position`, so the *targets* are fixed and only the *membership* is editable.
* Addressable slot space without touching any code: **3510 slots (index `$0000`–`$0DB5`), occupying
  `$3E8000`–`$3FFFFF` (96 KiB) at 28 bytes each, 8 spare `$FF` bytes at the end of each bank.**

**(d) Blank / unused slots in `$3E8000`–`$3FFFFF`.** Scanned all 3510 slots (`tools/glyphview.py blank`):

| metric | value |
|---|---|
| slots examined | 3510 |
| completely blank (28 × `$00`) | **1** — index `$0000` only (page 0) |
| near‑blank (≤ 6 lit pixels) | 8 (`$0000`, `$0001`, `$0003`, `$0004`, `$000A`, `$000C`, `$000D`, `$001D`) |
| duplicate bitmaps | 24 slots = 16 Cyrillic‑look‑alike‑of‑Latin + 8 solid `$FF` blocks (`$0DAE`–`$0DB5`, all equal to `$0DAD`) |
| distinct bitmaps | 3486 |
| zero bytes in `$3E8000`–`$3FFFFF` | 12.0 %, and the **longest contiguous zero run anywhere in the 96 KiB is 52 bytes** (at `$3E81F5`) — no free 28‑byte slot exists outside index `$0000` |
| free space elsewhere in the top 1 MiB | none — no zero run ≥ 2 KiB exists in `$300000`–`$3FFFFF`; banks `$F0`–`$FC` are high‑entropy data |

**The font is fully packed: there is effectively no unused glyph slot and no unused space.**

---

## 10. Verdicts on the prior claims

CONFIRMED
* LoROM mapping `file = (B-0x80)*0x8000 + (A & 0x7FFF)` (three in‑code proofs, §1).
* The drawing routine is entered at `$80:D23D` = **file `0x523D`** (the claimed `$D200`–`$D500` window is
  the right area; the actual index→address math is at `$D490` = file `0x5490`).
* `$D490` page/stride normalisation, **28‑byte stride**, `0x492` slots per page, 3 pages, base bank `$FD`,
  base file `0x3E8000`.
* Glyph bitmaps are **14×16 1bpp, big‑endian pixel order, top 14 bits of each row used** (rows stored as
  little‑endian 16‑bit words), placed at rows 1–14 of a 16×16 cell.
* A single‑byte redirect table exists: file `0x18000`, 96 entries × 2 bytes, big‑endian.
* The kana‑variant runtime redirect (`$D4BD`) exists, and `F0 AB` = あ (index `$0AB` = あ under the JIS  ku‑4 mapping).
* The prior anchor IDs `FC2A`=名, `F628`=字, `F40D`=教, `F812`=前, `FA34`=日 are **all correct**
  under the confirmed formula (名 = index `$0C2A` = JIS 44‑30, 字 = `$0628` = 27‑90, 教 = `$040D` =
  22‑21, 前 = `$0812` = 33‑16, 日 = `$0A34` = 38‑92) — each bitmap was rendered and read. The old
  notes were right about these five anchors; they were wrong about the *mechanism* that produced
  them. Additional anchors established here: `$01C5`=亜, `$039C`=帰, `$0546`=行, `$04D4`=言,
  `$08EC`=知, `$0AF2`=美, `$0DB5`=佰.

REFUTED
* "Bytes `$A0`–`$FC` + low byte form a 2‑byte kanji code." Only `$F0`+ does. `$A0`–`$E7` = phrase macros,
  `$E8`–`$EF` = sub‑table pointers, `$40`–`$9F` = single‑byte shortcuts, `$00`–`$3F` = control codes.
* Any ROWDELTA / per‑row‑delta glyph selection — the record is a flat 14 × 2‑byte bitmap, copied verbatim.
* "Kana table at file `0xD4E4`" — it is file **`0x54E4`** (`$80:D4E4`, bank `$80`).
* J2E (`reference/j2e_full/tokistuff_x/Offsets.txt`) font offsets `018200`, `1CCCA3`, `1CCD31` do **not**
  apply to this Rev‑1 ROM: the real tables are `0x18000`, `0x1CCAA5`, `0x2196A8`.

UNDETERMINED (not needed for injection)
* The exact semantics of the `$0153`–`$015A` half‑width extras and of the `$0A20`/`$0A24`/`$0A2A`
  BG‑map/tile‑allocator variables.
* Whether the shipped game ever sets `$0A2C` bit 4 in normal dialogue (the kana‑variant font is clearly
  used somewhere — the 76 remapped kana exist as real bitmaps at `$0D5A`+).

---

## 11. Practical consequence for a Chinese font

1. There is **no free glyph space**: 3510/3510 slots are populated (only index `$0000` is empty) and the
   rest of the top megabyte is dense data. Any Chinese bitmap font must **overwrite** the 96 KiB at
   `$3E8000`–`$3FFFFF` (or the ROM must be enlarged and `$D490` patched to add pages).
2. Because the 2‑byte code is *arithmetic*, a Chinese code→index assignment is completely free: choose any
   index in `$0000`–`$0DB5`, write the bitmap at `0x3E8000 + (index/0x492)*0x8000 + (index%0x492)*28`, and
   emit the two bytes `(0xF000+index) >> 8`, `(0xF000+index) & $FF` into the script.
3. The 14 × 14 usable ink area and the 16‑row cell (rows 1–14) are fixed by the hardware path
   (`$C100`/`$C11E` + 2×2 tile assembly), so a 14×14 1bpp cell is the maximum glyph size without further
   code changes.
4. If a 4th page is ever needed, `$D490` must be extended (one more `INX / TAY / SBC #$0492 / BCC` block and
   a bank seed below `$FD`) **and** the ROM enlarged — banks `$F8`–`$FC` are occupied.
