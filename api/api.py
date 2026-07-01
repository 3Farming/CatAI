from io import BytesIO
import os,  requests
from PIL import Image

output_dir = "./assets/brawler_icons2"
os.makedirs(output_dir, exist_ok=True)

brawlers_url = "https://api.brawlify.com/v1/brawlers"
brawlers_data = requests.get(brawlers_url).json()['list']

print(f"Start downloading icons for {len(brawlers_data)} brawlers...")

for brawler_obj in brawlers_data:
    icon_url = brawler_obj['imageUrl2']
    try:
        response = requests.get(icon_url)
        response.raise_for_status()
        
        image = Image.open(BytesIO(response.content))
        
        brawler_name = str(brawler_obj['name']).lower().strip()
        for symbol in [' ', '-', '.', '&', '/', '\\']:
            brawler_name = brawler_name.replace(symbol, "")
            
        file_path = os.path.join(output_dir, f"{brawler_name}.png")
        image.save(file_path)
        print(f"Brawler icon {brawler_name} saved successfully.")
        
    except Exception as e:
        print(f"Error processing brawler {brawler_obj.get('name')}: {e}")

print("All available icons have been loaded successfully!")

