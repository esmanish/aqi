import os, requests, time, json, math

BOUNDS = {'north': 13.018, 'south': 13.004, 'east': 74.802, 'west': 74.780}
MIN_ZOOM, MAX_ZOOM = 14, 19

def lat_lon_to_tile(lat, lon, z):
    n = 2.0 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y

print("Downloading NITK campus tiles...")
total, downloaded = 0, 0

for z in range(MIN_ZOOM, MAX_ZOOM + 1):
    x_min, y_max = lat_lon_to_tile(BOUNDS['south'], BOUNDS['west'], z)
    x_max, y_min = lat_lon_to_tile(BOUNDS['north'], BOUNDS['east'], z)
    total += (x_max - x_min + 1) * (y_max - y_min + 1)

for z in range(MIN_ZOOM, MAX_ZOOM + 1):
    x_min, y_max = lat_lon_to_tile(BOUNDS['south'], BOUNDS['west'], z)
    x_max, y_min = lat_lon_to_tile(BOUNDS['north'], BOUNDS['east'], z)
    
    for x in range(x_min, x_max + 1):
        os.makedirs(f'static/tiles/{z}/{x}', exist_ok=True)
        for y in range(y_min, y_max + 1):
            file_path = f'static/tiles/{z}/{x}/{y}.png'
            if not os.path.exists(file_path):
                try:
                    r = requests.get(f'https://tile.openstreetmap.org/{z}/{x}/{y}.png', 
                                   headers={'User-Agent': 'NITK-AQ-System'})
                    with open(file_path, 'wb') as f:
                        f.write(r.content)
                    time.sleep(0.1)
                except: pass
            downloaded += 1
            print(f'\rProgress: {downloaded}/{total} ({downloaded/total*100:.1f}%)', end='')

with open('static/tiles/metadata.json', 'w') as f:
    json.dump({'bounds': BOUNDS, 'total': total, 'date': time.strftime('%Y-%m-%d')}, f)
print("\nDownload complete!")