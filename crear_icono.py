from PIL import Image, ImageDraw

# Icono RAM chip 256x256
img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Fondo redondeado
d.rounded_rectangle([8, 8, 248, 248], radius=48, fill=(30, 30, 46, 255))

# Chip
d.rounded_rectangle([64, 80, 192, 200], radius=12, fill=(0, 212, 164, 255))
d.rounded_rectangle([84, 100, 172, 150], radius=6, fill=(30, 30, 46, 255))
# Pines
for x in range(80, 185, 20):
    d.rectangle([x, 66, x+10, 80], fill=(0, 212, 164, 255))
    d.rectangle([x, 200, x+10, 214], fill=(0, 212, 164, 255))
# Texto RAM
d.text((96, 112), "RAM", fill=(0, 212, 164, 255))
# Rayo
d.polygon([(128, 155), (112, 185), (128, 185), (124, 210), (148, 178), (132, 178)], fill=(255, 255, 255, 255))

img.save("icono.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
img.save("icono.png")
print("icono.ico creado OK")
