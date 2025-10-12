# Biblioteca OLED optimizada para XBee3
class OLED:
    def __init__(self, i2c, a=0x3C):
        self.w = 128
        self.h = 32
        self.p = self.h // 8
        self.i2c = i2c
        self.a = a
        self.b = bytearray(self.p * self.w)
        # Init
        cmds = bytearray([0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, 0x3F, 0xC8,
                         0xD3, 0x00, 0xDA, 0x12, 0xD5, 0x80, 0xD9, 0xF1,
                         0xDB, 0x30, 0x81, 0xFF, 0xA4, 0xA6, 0x8D, 0x14, 0xAF])
        for i in range(len(cmds)):
            self.cmd(cmds[i])
        self.clr()
        self.show()
    
    def cmd(self, c):
        self.i2c.writeto(self.a, bytearray([0x80, c]))
    
    def clr(self):
        for i in range(len(self.b)):
            self.b[i] = 0
    
    def show(self):
        self.cmd(0x21)
        self.cmd(0)
        self.cmd(self.w - 1)
        self.cmd(0x22)
        self.cmd(0)
        self.cmd(self.p - 1)
        for i in range(0, len(self.b), 16):
            end = min(i + 16, len(self.b))
            self.i2c.writeto(self.a, b'\x40' + self.b[i:end])
    
    # Mapa de caracteres reducido - solo los esenciales
    F = {
        'A': bytearray([0x7E, 0x09, 0x09, 0x7E]),
        'B': bytearray([0x7F, 0x49, 0x49, 0x36]),
        'C': bytearray([0x3E, 0x41, 0x41, 0x22]),
        'D': bytearray([0x7F, 0x41, 0x41, 0x3E]),
        'E': bytearray([0x7F, 0x49, 0x49, 0x41]),
        'F': bytearray([0x7F, 0x09, 0x09, 0x01]),
        'I': bytearray([0x41, 0x7F, 0x41, 0x00]),
        'K': bytearray([0x7F, 0x08, 0x14, 0x63]),
        'L': bytearray([0x7F, 0x40, 0x40, 0x40]),
        'M': bytearray([0x7F, 0x02, 0x04, 0x02, 0x7F]),
        'N': bytearray([0x7F, 0x04, 0x08, 0x10, 0x7F]),
        'O': bytearray([0x3E, 0x41, 0x41, 0x3E]),
        'P': bytearray([0x7F, 0x09, 0x09, 0x06]),
        'R': bytearray([0x7F, 0x09, 0x19, 0x66]),
        'T': bytearray([0x01, 0x01, 0x7F, 0x01, 0x01]),
        'V': bytearray([0x1F, 0x20, 0x40, 0x20, 0x1F]),
        '0': bytearray([0x3E, 0x41, 0x41, 0x3E]),
        '1': bytearray([0x00, 0x21, 0x7F, 0x01]),
        '2': bytearray([0x39, 0x45, 0x43, 0x21]),
        '3': bytearray([0x22, 0x41, 0x49, 0x36]),
        '4': bytearray([0x0C, 0x14, 0x24, 0x7F]),
        '5': bytearray([0x72, 0x51, 0x51, 0x4E]),
        '6': bytearray([0x3E, 0x49, 0x49, 0x26]),
        '7': bytearray([0x01, 0x01, 0x79, 0x07]),
        '8': bytearray([0x36, 0x49, 0x49, 0x36]),
        '9': bytearray([0x06, 0x49, 0x49, 0x3E]),
        '.': bytearray([0x00, 0x60, 0x60, 0x00]),
        ':': bytearray([0x00, 0x36, 0x36, 0x00]),
        '>': bytearray([0x41, 0x22, 0x14, 0x08]),
        ' ': bytearray([0x00, 0x00, 0x00, 0x00]),
        '-': bytearray([0x08, 0x08, 0x08, 0x08]),
        '/': bytearray([0x20, 0x10, 0x08, 0x04]),
    }
    
    def menu(self, ops, pos, sts=""):
        self.clr()
        self.txt("TELEMANDO", 20, 0)  # Título en la primera línea
        
        # Línea separadora en la segunda línea
        for i in range(self.w):
            self.b[i + self.w] = 0x01
        
        # Asegurarnos que todas las opciones se muestran con espaciado correcto
        for i, op in enumerate(ops):
            if i < 3:  # Máximo 3 opciones
                y = 16 + (i * 8)  # Tercera línea y siguientes
                
                # Limitar longitud y añadir espaciado correcto
                text_to_show = op[:10]
                
                # Mostrar texto de opción con mejor espaciado
                self.txt(text_to_show, 8, y)
                
                # Mostrar flecha de selección a la derecha
                if i == pos:
                    self.txt(">", self.w - 8, y)
        
        # Estado en la parte inferior
        if sts:
            self.txt(sts[:8], 32, self.h - 8)
        
        # Forzar actualización de pantalla    
        self.show()

    def txt(self, s, x, y):
        pos = x
        page = y // 8
        for c in s.upper():
            if c in self.F:
                p = self.F[c]
                for col in range(len(p)):
                    if pos < self.w:
                        idx = page * self.w + pos
                        if idx < len(self.b):
                            self.b[idx] = p[col]
                        pos += 1
                # Añadir espacio entre caracteres
                pos += 1
            else:
                # Espacio para caracteres no definidos
                pos += 3

    def stdby(self, bat):
        self.clr()
        self.txt("TELEMANDO", 20, 8)
        self.txt(bat, 20, 24)
        self.show()