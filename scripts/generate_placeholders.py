"""Helper to generate minimal clean placeholder WebP images with paper tone and room title."""
from PIL import Image, ImageDraw, ImageFont
import os

def create_placeholder(filename, text, size=(1200, 800)):
    # Canvas with --color-paper-dark (#ECE4D6)
    img = Image.new("RGB", size, color="#ECE4D6")
    draw = ImageDraw.Draw(img)
    
    # Inner border with --color-border-dark (#2A1F1A)
    draw.rectangle([20, 20, size[0]-20, size[1]-20], outline="#2A1F1A", width=2)
    draw.rectangle([26, 26, size[0]-26, size[1]-26], outline="#7A6C62", width=1)
    
    # Text
    draw.text((size[0]//2, size[1]//2 - 30), "PLANTATION STAY", fill="#7A6C62", anchor="mm")
    draw.text((size[0]//2, size[1]//2 + 20), text, fill="#2A1F1A", anchor="mm")
    draw.text((size[0]//2, size[1]//2 + 70), "Chikkamagaluru, Karnataka", fill="#7A6C62", anchor="mm")
    
    os.makedirs("app/static/images", exist_ok=True)
    img.save(f"app/static/images/{filename}", "WEBP", quality=85)
    print(f"Generated app/static/images/{filename}")

if __name__ == "__main__":
    create_placeholder("estate-hero.webp", "COFFEE ESTATE GROUNDS", (1600, 900))
    create_placeholder("estate-room.webp", "ESTATE ROOM", (1200, 800))
    create_placeholder("luxury-villa.webp", "LUXURY PLANTATION VILLA", (1200, 800))
    create_placeholder("estate-room-thumb.webp", "ESTATE ROOM", (400, 300))
    create_placeholder("luxury-villa-thumb.webp", "LUXURY PLANTATION VILLA", (400, 300))

