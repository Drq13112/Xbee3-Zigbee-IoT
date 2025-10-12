# framebuf.py - minimal compatible with SSD1306

MONO_HLSB = 0
MONO_VLSB = 1

# Compact 8x8 font as a single bytes object to save memory
FONT_DATA = bytes([
    # A-Z (0-25)
    0x7E, 0x09, 0x09, 0x7E, 0x00, 0x00, 0x00, 0x00,  # A
    0x7F, 0x49, 0x49, 0x36, 0x00, 0x00, 0x00, 0x00,  # B
    0x3E, 0x41, 0x41, 0x22, 0x00, 0x00, 0x00, 0x00,  # C
    0x7F, 0x41, 0x41, 0x3E, 0x00, 0x00, 0x00, 0x00,  # D
    0x7F, 0x49, 0x49, 0x41, 0x00, 0x00, 0x00, 0x00,  # E
    0x7F, 0x09, 0x09, 0x01, 0x00, 0x00, 0x00, 0x00,  # F
    0x3E, 0x41, 0x49, 0x3A, 0x00, 0x00, 0x00, 0x00,  # G
    0x7F, 0x08, 0x08, 0x7F, 0x00, 0x00, 0x00, 0x00,  # H
    0x41, 0x7F, 0x41, 0x00, 0x00, 0x00, 0x00, 0x00,  # I
    0x20, 0x40, 0x41, 0x3F, 0x00, 0x00, 0x00, 0x00,  # J
    0x7F, 0x08, 0x14, 0x63, 0x00, 0x00, 0x00, 0x00,  # K
    0x7F, 0x40, 0x40, 0x40, 0x00, 0x00, 0x00, 0x00,  # L
    0x7F, 0x02, 0x04, 0x02, 0x7F, 0x00, 0x00, 0x00,  # M
    0x7F, 0x04, 0x08, 0x10, 0x7F, 0x00, 0x00, 0x00,  # N
    0x3E, 0x41, 0x41, 0x3E, 0x00, 0x00, 0x00, 0x00,  # O
    0x7F, 0x09, 0x09, 0x06, 0x00, 0x00, 0x00, 0x00,  # P
    0x3E, 0x41, 0x51, 0xBE, 0x00, 0x00, 0x00, 0x00,  # Q
    0x7F, 0x09, 0x19, 0x66, 0x00, 0x00, 0x00, 0x00,  # R
    0x46, 0x49, 0x49, 0x31, 0x00, 0x00, 0x00, 0x00,  # S
    0x01, 0x01, 0x7F, 0x01, 0x01, 0x00, 0x00, 0x00,  # T
    0x3F, 0x40, 0x40, 0x3F, 0x00, 0x00, 0x00, 0x00,  # U
    0x1F, 0x20, 0x40, 0x20, 0x1F, 0x00, 0x00, 0x00,  # V
    0x3F, 0x40, 0x38, 0x40, 0x3F, 0x00, 0x00, 0x00,  # W
    0x63, 0x14, 0x08, 0x14, 0x63, 0x00, 0x00, 0x00,  # X
    0x07, 0x08, 0x70, 0x08, 0x07, 0x00, 0x00, 0x00,  # Y
    0x61, 0x51, 0x49, 0x45, 0x43, 0x00, 0x00, 0x00,  # Z
    # 0-9 (26-35)
    0x3E, 0x41, 0x41, 0x3E, 0x00, 0x00, 0x00, 0x00,  # 0
    0x00, 0x84, 0xFE, 0x80, 0x00, 0x00, 0x00, 0x00,  # 1
    0x84, 0xC2, 0xA2, 0x9C, 0x00, 0x00, 0x00, 0x00,  # 2 
    0x22, 0x41, 0x49, 0x36, 0x00, 0x00, 0x00, 0x00,  # 3
    0x30, 0x28, 0x24, 0xFE, 0x00, 0x00, 0x00, 0x00,  # 4
    0x72, 0x51, 0x51, 0x4E, 0x00, 0x00, 0x00, 0x00,  # 5
    0x7C, 0x92, 0x92, 0x64, 0x00, 0x00, 0x00, 0x00,  # 6
    0x01, 0x01, 0x79, 0x07, 0x00, 0x00, 0x00, 0x00,  # 7
    0x36, 0x49, 0x49, 0x36, 0x00, 0x00, 0x00, 0x00,  # 8
    0x06, 0x49, 0x49, 0x3E, 0x00, 0x00, 0x00, 0x00,  # 9
    # Symbols (36-42)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # space
    0x00, 0x60, 0x60, 0x00, 0x00, 0x00, 0x00, 0x00,  # .
    0x00, 0x36, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00,  # :
    0x41, 0x22, 0x14, 0x08, 0x00, 0x00, 0x00, 0x00,  # >
    0x08, 0x14, 0x22, 0x41, 0x00, 0x00, 0x00, 0x00,  # <
    0x08, 0x08, 0x08, 0x08, 0x00, 0x00, 0x00, 0x00,  # -
    0x20, 0x10, 0x08, 0x04, 0x00, 0x00, 0x00, 0x00,  # /
])

class FrameBuffer:
    def __init__(self, buffer, width, height, format):
        self.buffer = buffer
        self.width = width
        self.height = height
        self.format = format
        self.stride = len(buffer) // height if height > 0 else 0

    # PIXEL
    def pixel(self, x, y, color=1):
        if 0 <= x < self.width and 0 <= y < self.height:
            if self.format == MONO_VLSB:
                index = (y >> 3) * self.width + x
                bit = y & 7
            elif self.format == MONO_HLSB:
                index = (x >> 3) + (y * (self.width // 8))
                bit = x & 7
            else:
                return
            if color:
                self.buffer[index] |= (1 << bit)
            else:
                self.buffer[index] &= ~(1 << bit)

    # FILL
    def fill(self, color):
        val = 0xFF if color else 0x00
        for i in range(len(self.buffer)):
            self.buffer[i] = val

    # HLINE
    def hline(self, x, y, w, color=1):
        for i in range(w):
            self.pixel(x + i, y, color)

    # VLINE
    def vline(self, x, y, h, color=1):
        for i in range(h):
            self.pixel(x, y + i, color)

    # LINE
    def line(self, x0, y0, x1, y1, color=1):
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    # RECT
    def rect(self, x, y, w, h, color=1):
        self.hline(x, y, w, color)
        self.hline(x, y + h - 1, w, color)
        self.vline(x, y, h, color)
        self.vline(x + w - 1, y, h, color)

    # FILL RECT
    def fill_rect(self, x, y, w, h, color=1):
        for i in range(h):
            self.hline(x, y + i, w, color)

    # CIRCLE
    def circle(self, x0, y0, r, color=1):
        f = 1 - r
        dx = 1
        dy = -2 * r
        x = 0
        y = r
        self.pixel(x0, y0 + r, color)
        self.pixel(x0, y0 - r, color)
        self.pixel(x0 + r, y0, color)
        self.pixel(x0 - r, y0, color)
        while x < y:
            if f >= 0:
                y -= 1
                dy += 2
                f += dy
            x += 1
            dx += 2
            f += dx
            self.pixel(x0 + x, y0 + y, color)
            self.pixel(x0 - x, y0 + y, color)
            self.pixel(x0 + x, y0 - y, color)
            self.pixel(x0 - x, y0 - y, color)
            self.pixel(x0 + y, y0 + x, color)
            self.pixel(x0 - y, y0 + x, color)
            self.pixel(x0 + y, y0 - x, color)
            self.pixel(x0 - y, y0 - x, color)

    # FILL CIRCLE
    def fill_circle(self, x0, y0, r, color=1):
        for y in range(-r, r + 1):
            for x in range(-r, r + 1):
                if x * x + y * y <= r * r:
                    self.pixel(x0 + x, y0 + y, color)

    # BLIT
    def blit(self, source, x, y):
        for j in range(source.height):
            for i in range(source.width):
                if 0 <= x + i < self.width and 0 <= y + j < self.height:
                    # Assuming source is also MONO_VLSB or compatible; adjust if needed
                    if source.format == MONO_VLSB:
                        s_index = (j >> 3) * source.width + i
                        s_bit = j & 7
                        val = (source.buffer[s_index] >> s_bit) & 1
                    elif source.format == MONO_HLSB:
                        s_index = (i >> 3) + (j * (source.width // 8))
                        s_bit = i & 7
                        val = (source.buffer[s_index] >> s_bit) & 1
                    else:
                        val = 0
                    self.pixel(x + i, y + j, val)

    # TEXT
    def text(self, s, x, y, col=1):
        pos = x
        for c in s.upper():
            idx = -1
            if 'A' <= c <= 'Z':
                idx = ord(c) - ord('A')
            elif '0' <= c <= '9':
                idx = 26 + ord(c) - ord('0')
            elif c == ' ':
                idx = 36
            elif c == '.':
                idx = 37
            elif c == ':':
                idx = 38
            elif c == '>':
                idx = 39
            elif c == '<':
                idx = 40
            elif c == '-':
                idx = 41
            elif c == '/':
                idx = 42
            if idx >= 0:
                start = idx * 8
                p = FONT_DATA[start:start+8]
                for col_idx in range(8):
                    byte = p[col_idx]
                    for row in range(8):
                        if byte & (1 << row):
                            self.pixel(pos + col_idx, y + row, col)
            pos += 8