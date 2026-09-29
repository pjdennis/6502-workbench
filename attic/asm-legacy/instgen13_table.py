#!/usr/bin/env python3

# ===== Scramble table from hash_table13.asm =====

SCRAMBLE_TABLE = [
    0x01,
    0x20,
    0x33,
    0x1B,
    0x1C,
    0x16,
    0x29,
    0x1F,
    0x3A,
    0x75,
    0x62,
    0x42,
    0x68,
    0x79,
    0x00,
    0x52,
    0x32,
    0x0B,
    0x22,
    0x77,
    0x72,
    0x71,
    0x10,
    0x59,
    0x06,
    0x4D,
    0x17,
    0x37,
    0x40,
    0x0C,
    0x66,
    0x21,
    0x1E,
    0x43,
    0x3E,
    0x30,
    0x13,
    0x07,
    0x7E,
    0x44,
    0x6C,
    0x58,
    0x15,
    0x1A,
    0x5A,
    0x24,
    0x0F,
    0x7A,
    0x7B,
    0x39,
    0x4B,
    0x53,
    0x70,
    0x73,
    0x19,
    0x69,
    0x55,
    0x7D,
    0x4C,
    0x2C,
    0x7C,
    0x47,
    0x23,
    0x61,
    0x56,
    0x48,
    0x74,
    0x2F,
    0x76,
    0x26,
    0x2E,
    0x2B,
    0x6B,
    0x57,
    0x12,
    0x4F,
    0x25,
    0x64,
    0x0A,
    0x27,
    0x50,
    0x65,
    0x5D,
    0x31,
    0x2A,
    0x46,
    0x6F,
    0x5F,
    0x67,
    0x54,
    0x18,
    0x49,
    0x05,
    0x11,
    0x03,
    0x6E,
    0x02,
    0x0E,
    0x34,
    0x5E,
    0x63,
    0x08,
    0x6D,
    0x14,
    0x6A,
    0x0D,
    0x3B,
    0x4E,
    0x3D,
    0x60,
    0x41,
    0x38,
    0x45,
    0x7F,
    0x3F,
    0x3C,
    0x5C,
    0x2D,
    0x35,
    0x51,
    0x04,
    0x28,
    0x09,
    0x4A,
    0x78,
    0x1D,
    0x36,
    0x5B,
]

# ===== MNTAB from instgen13.asm =====
# Each tuple is: (mnemonic, byte1, byte2, opcode)
# In instgen13, byte1 -> HEX2 (HT_VL), byte2 -> HEX1 (HT_VH); opcode byte is not used in the hash table value.

MNTAB = [
    ("ADC#", 0x00, 0x04, 0x69),
    ("ADCZ", 0x00, 0x04, 0x65),
    ("AND#", 0x00, 0x04, 0x29),
    ("ASLA", 0x00, 0x00, 0x0A),
    ("ASLZ", 0x00, 0x04, 0x06),
    ("BCC", 0x00, 0x02, 0x90),
    ("BCS", 0x00, 0x02, 0xB0),
    ("BEQ", 0x00, 0x02, 0xF0),
    ("BITZ", 0x00, 0x04, 0x24),
    ("BMI", 0x00, 0x02, 0x30),
    ("BNE", 0x00, 0x02, 0xD0),
    ("BPL", 0x00, 0x02, 0x10),
    ("BRK", 0x00, 0x00, 0x00),
    ("CLC", 0x00, 0x00, 0x18),
    ("CMPZ", 0x00, 0x04, 0xC5),
    ("CMP#", 0x00, 0x04, 0xC9),
    ("CMP,Y", 0x00, 0x00, 0xD9),
    ("CPXZ", 0x00, 0x04, 0xE4),
    ("CPYZ", 0x00, 0x04, 0xC4),
    ("CPY#", 0x00, 0x04, 0xC0),
    ("DECZ", 0x00, 0x04, 0xC6),
    ("DEX", 0x00, 0x00, 0xCA),
    ("DEY", 0x00, 0x00, 0x88),
    ("EORZ", 0x00, 0x04, 0x45),
    ("INCZ", 0x00, 0x04, 0xE6),
    ("INX", 0x00, 0x00, 0xE8),
    ("INY", 0x00, 0x00, 0xC8),
    ("JMP", 0x00, 0x00, 0x4C),
    ("JSR", 0x00, 0x00, 0x20),
    ("LDA", 0x00, 0x00, 0xAD),
    ("LDX", 0x00, 0x00, 0xAE),
    ("LDY", 0x00, 0x00, 0xAC),
    ("LDA#", 0x00, 0x04, 0xA9),
    ("LDAZ(),Y", 0x00, 0x04, 0xB1),
    ("LDA,X", 0x00, 0x00, 0xBD),
    ("LDA,Y", 0x00, 0x00, 0xB9),
    ("LDAZ", 0x00, 0x04, 0xA5),
    ("LDAZ,X", 0x00, 0x04, 0xB5),
    ("LDXZ", 0x00, 0x04, 0xA6),
    ("LDYZ", 0x00, 0x04, 0xA4),
    ("LDX#", 0x00, 0x04, 0xA2),
    ("LDY#", 0x00, 0x04, 0xA0),
    ("LSRA", 0x00, 0x00, 0x4A),
    ("ORAZ", 0x00, 0x04, 0x05),
    ("PHA", 0x00, 0x00, 0x48),
    ("PLA", 0x00, 0x00, 0x68),
    ("ROLZ", 0x00, 0x04, 0x26),
    ("RTS", 0x00, 0x00, 0x60),
    ("SBC#", 0x00, 0x04, 0xE9),
    ("SBCZ", 0x00, 0x04, 0xE5),
    ("SEC", 0x00, 0x00, 0x38),
    ("STA", 0x00, 0x00, 0x8D),
    ("STAZ(),Y", 0x00, 0x04, 0x91),
    ("STA,X", 0x00, 0x00, 0x9D),
    ("STA,Y", 0x00, 0x00, 0x99),
    ("STAZ", 0x00, 0x04, 0x85),
    ("STAZ,X", 0x00, 0x04, 0x95),
    ("STXZ", 0x00, 0x04, 0x86),
    ("STYZ", 0x00, 0x04, 0x84),
    ("TAX", 0x00, 0x00, 0xAA),
    ("TAY", 0x00, 0x00, 0xA8),
    ("TSX", 0x00, 0x00, 0xBA),
    ("TXA", 0x00, 0x00, 0x8A),
    ("TYA", 0x00, 0x00, 0x98),
    ("DATA", 0x00, 0x01, 0x00),   # directive
]

# ===== Hash + heap builder =====

def calc_hash(token_bytes):
    """
    Implements calculate_hash from hash_table13.asm.
    token_bytes: list of integer bytes, including terminating 0.
    """
    h = 0
    for b in token_bytes:
        if b == 0:
            break
        a = b & 0x7F
        a ^= h
        h = SCRAMBLE_TABLE[a]
    h = (h << 1) & 0xFF  # ASL HASH
    return h  # this is the byte offset into IHASHTAB

# IHASHTAB is 256 bytes = 128 entries * 2 bytes each
IHASHTAB = [0] * 256  # byte array
HEAP = []             # byte array for entries
ENTRY_STARTS = []     # list of entry start addresses (heap indices)


def add_instruction(name: str, ht_vl: int, ht_vh: int):
    """
    Models hash_add + store_token + store_hash_entry/store_table_entry.

    Entry layout in HEAP:
        [0..1] : next pointer (lo, hi)
        [2..] : token string (ASCII) + 0
        [...] : HT_VL, HT_VH (2 bytes)
    """
    # Build key (HT_KEY) as bytes + 0
    token = [ord(c) for c in name] + [0]

    # Start address for this entry
    ptr = len(HEAP)
    ENTRY_STARTS.append(ptr)

    # Store null 'next' pointer
    HEAP.extend([0, 0])

    # Store token (mnemonic + 0)
    HEAP.extend(token)

    # Store value (HT_VL, HT_VH)
    HEAP.extend([ht_vl & 0xFF, ht_vh & 0xFF])

    # Calculate hash
    h = calc_hash(token)   # byte offset in IHASHTAB
    off = h
    lo = IHASHTAB[off]
    hi = IHASHTAB[off + 1]
    head_ptr = lo | (hi << 8)

    if head_ptr == 0:
        # Empty bucket: store hash entry directly
        IHASHTAB[off] = ptr & 0xFF
        IHASHTAB[off + 1] = (ptr >> 8) & 0xFF
    else:
        # Collision: traverse to end of chain and link
        cur = head_ptr
        while True:
            nlo = HEAP[cur]
            nhi = HEAP[cur + 1]
            nxt = nlo | (nhi << 8)
            if nxt == 0:
                HEAP[cur] = ptr & 0xFF
                HEAP[cur + 1] = (ptr >> 8) & 0xFF
                break
            cur = nxt


def decode_name_at(ptr: int) -> str:
    """Read mnemonic from HEAP starting at entry pointer ptr."""
    p = ptr + 2  # skip next pointer
    chars = []
    while p < len(HEAP):
        b = HEAP[p]
        if b == 0:
            break
        chars.append(b)
        p += 1
    return "".join(chr(c) for c in chars)


def entry_value_bytes(ptr: int):
    """Return (vl, vh) stored at the end of an entry."""
    p = ptr + 2
    while HEAP[p] != 0:
        p += 1
    p += 1  # move past terminator
    vl = HEAP[p]
    vh = HEAP[p + 1]
    return vl, vh


def build_tables():
    for name, b1, b2, _opcode in MNTAB:
        # In instgen13: HT_VL = HEX2 = first byte after string (b1),
        #               HT_VH = HEX1 = second byte after string (b2).
        add_instruction(name, ht_vl=b1, ht_vh=b2)


def print_hash_table():
    print("IHASHTAB")
    # 128 entries, 8 per row
    rows = []
    for bucket in range(128):
        off = bucket * 2
        lo = IHASHTAB[off]
        hi = IHASHTAB[off + 1]
        ptr = lo | (hi << 8)
        if ptr == 0:
            rows.append("$0000")
        else:
            rows.append("i_" + decode_name_at(ptr))

    for i in range(0, 128, 8):
        chunk = rows[i : i + 8]
        print("  DATA " + " ".join(f"{item:>8}" for item in chunk))


def print_heap():
    print("; Instructions heap data")
    for ptr in ENTRY_STARTS:
        name = decode_name_at(ptr)
        nxt = HEAP[ptr] | (HEAP[ptr + 1] << 8)
        vl, vh = entry_value_bytes(ptr)

        print(f"i_{name}")
        if nxt == 0:
            print("  DATA $0000")
        else:
            print(f"  DATA i_{decode_name_at(nxt)}")

        # This mirrors the idea of: DATA $00 <HT_VL> <HT_VH>
        # (instgen prints the first $00 via LDA #$00 / display_byte,
        # then the two value bytes from the entry).
        print(f"  DATA $00 ${vl:02X} ${vh:02X}")


if __name__ == "__main__":
    build_tables()
    print_hash_table()
    print()
    print_heap()
