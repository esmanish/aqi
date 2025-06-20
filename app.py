from flask import Flask, render_template, jsonify, send_file, request
import sqlite3, json, os, time, math, random
from datetime import datetime
import threading

# Try hardware imports
try:
    import RPi.GPIO as GPIO
    import board
    import adafruit_dht
    HAS_SENSORS = True
except ImportError:
    HAS_SENSORS = False
    print("Running in simulation mode")

app = Flask(__name__)

# Constants
BOUNDS = {'north': 13.018, 'south': 13.004, 'east': 74.802, 'west': 74.780}
SENSOR_DATA = {'pm25': 0, 'pm10': 0, 'temp': 0, 'humidity': 0, 'aqi': 0}
SENSOR_LOCK = threading.Lock()
dht22 = None

def init_db():
    conn = sqlite3.connect('data/air_quality.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS readings
                    (id INTEGER PRIMARY KEY, location TEXT, lat REAL, lng REAL,
                     aqi INTEGER, pm25 REAL, pm10 REAL, temp REAL, humidity REAL,
                     timestamp REAL)''')
    conn.commit()
    conn.close()

def setup_sensors():
    global dht22
    if not HAS_SENSORS:
        return
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(18, GPIO.IN)  # PM2.5
        GPIO.setup(19, GPIO.IN)  # PM10
        dht22 = adafruit_dht.DHT22(board.D27)
        print("Sensors initialized")
    except Exception as e:
        print(f"Sensor setup failed: {e}")

def read_dust_sensor(pin, duration=3):
    if not HAS_SENSORS:
        return random.uniform(5, 15)
    
    start_time = time.time()
    low_time = 0
    
    while (time.time() - start_time) < duration:
        if GPIO.input(pin) == 0:
            low_time += 0.01
        time.sleep(0.01)
    
    ratio = (low_time / duration) * 100
    return min(max(ratio, 0), 30.0)

def calculate_aqi(pm25):
    if pm25 <= 12.0: 
        return int((50/12.0) * pm25)
    elif pm25 <= 35.4: 
        return int(50 + ((100-50)/(35.4-12.0)) * (pm25-12.0))
    elif pm25 <= 55.4: 
        return int(100 + ((150-100)/(55.4-35.4)) * (pm25-35.4))
    elif pm25 <= 150.4: 
        return int(150 + ((200-150)/(150.4-55.4)) * (pm25-55.4))
    elif pm25 <= 250.4: 
        return int(200 + ((300-200)/(250.4-150.4)) * (pm25-150.4))
    else: 
        return min(int(300 + ((500-300)/(500.4-250.4)) * (pm25-250.4)), 500)

def continuous_sensor_reading():
    global SENSOR_DATA
    setup_sensors()
    
    # Moving average buffers
    pm25_buffer = []
    pm10_buffer = []
    temp_buffer = []
    humidity_buffer = []
    buffer_size = 5
    
    while True:
        try:
            if HAS_SENSORS and dht22:
                # Read DHT22 with retry
                temp = humidity = None
                for _ in range(3):
                    try:
                        temp = dht22.temperature
                        humidity = dht22.humidity
                        if temp and humidity:
                            break
                    except:
                        time.sleep(0.5)
                
                # Read dust sensors
                pm25_ratio = read_dust_sensor(18, 3)
                pm10_ratio = read_dust_sensor(19, 3)
                pm25 = pm25_ratio * 0.1 * 10
                pm10 = pm10_ratio * 0.1 * 12
            else:
                # Simulation with stability
                base_pm25 = 20 + 10 * math.sin(time.time() / 3600)
                pm25 = max(5, base_pm25 + random.uniform(-2, 2))
                pm10 = pm25 * 1.5 + random.uniform(-3, 3)
                temp = 28 + 3 * math.sin(time.time() / 7200) + random.uniform(-0.5, 0.5)
                humidity = 65 + 10 * math.sin(time.time() / 5400) + random.uniform(-2, 2)
            
            # Add to buffers
            if pm25: pm25_buffer.append(pm25)
            if pm10: pm10_buffer.append(pm10)
            if temp: temp_buffer.append(temp)
            if humidity: humidity_buffer.append(humidity)
            
            # Keep buffer size limited
            if len(pm25_buffer) > buffer_size: pm25_buffer.pop(0)
            if len(pm10_buffer) > buffer_size: pm10_buffer.pop(0)
            if len(temp_buffer) > buffer_size: temp_buffer.pop(0)
            if len(humidity_buffer) > buffer_size: humidity_buffer.pop(0)
            
            # Calculate averages
            with SENSOR_LOCK:
                SENSOR_DATA['pm25'] = round(sum(pm25_buffer) / len(pm25_buffer), 1) if pm25_buffer else 0
                SENSOR_DATA['pm10'] = round(sum(pm10_buffer) / len(pm10_buffer), 1) if pm10_buffer else 0
                SENSOR_DATA['temp'] = round(sum(temp_buffer) / len(temp_buffer), 1) if temp_buffer else 0
                SENSOR_DATA['humidity'] = round(sum(humidity_buffer) / len(humidity_buffer), 0) if humidity_buffer else 0
                SENSOR_DATA['aqi'] = calculate_aqi(SENSOR_DATA['pm25'])
            
            time.sleep(5)  # Update every 5 seconds
            
        except Exception as e:
            print(f"Sensor reading error: {e}")
            time.sleep(5)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def serve_tile(z, x, y):
    tile_path = f'static/tiles/{z}/{x}/{y}.png'
    if os.path.exists(tile_path) and is_tile_in_bounds(x, y, z):
        return send_file(tile_path, mimetype='image/png')
    return send_file('static/blank_tile.png', mimetype='image/png')

def is_tile_in_bounds(x, y, z):
    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return not (lon_max < BOUNDS['west'] or lon_min > BOUNDS['east'] or 
                lat_max < BOUNDS['south'] or lat_min > BOUNDS['north'])

@app.route('/api/realtime')
def realtime_data():
    with SENSOR_LOCK:
        return jsonify({
            'pm25': SENSOR_DATA['pm25'],
            'pm10': SENSOR_DATA['pm10'],
            'temperature': SENSOR_DATA['temp'],
            'humidity': SENSOR_DATA['humidity'],
            'aqi': SENSOR_DATA['aqi'],
            'timestamp': datetime.now().isoformat()
        })

@app.route('/api/collect', methods=['POST'])
def collect_data():
    req = request.json
    
    # Validate coordinates
    lat = float(req['latitude'])
    lng = float(req['longitude'])
    if not (BOUNDS['south'] <= lat <= BOUNDS['north'] and 
            BOUNDS['west'] <= lng <= BOUNDS['east']):
        return jsonify({'error': 'Location outside campus bounds'}), 400
    
    with SENSOR_LOCK:
        current_data = SENSOR_DATA.copy()
    
    conn = sqlite3.connect('data/air_quality.db')
    conn.execute('''INSERT INTO readings (location, lat, lng, aqi, pm25, pm10, temp, humidity, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (req['locationName'], lat, lng, current_data['aqi'],
                  current_data['pm25'], current_data['pm10'], 
                  current_data['temp'], current_data['humidity'], time.time()))
    conn.commit()
    conn.close()
    
    return jsonify({
        **current_data,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'location': req['locationName']
    })

@app.route('/api/status')
def system_status():
    conn = sqlite3.connect('data/air_quality.db')
    count = conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
    conn.close()
    
    return jsonify({
        'sensors': 'hardware' if HAS_SENSORS else 'simulation',
        'database': 'connected',
        'reading_count': count,
        'sensor_status': 'active' if any(SENSOR_DATA.values()) else 'initializing'
    })

@app.route('/api/map-status')
def map_status():
    tile_count = sum(1 for root, dirs, files in os.walk('static/tiles') 
                     for f in files if f.endswith('.png'))
    return jsonify({
        'ready': True,
        'available_tiles': tile_count,
        'progress': {'downloaded': tile_count, 'total': tile_count, 'percentage': 100}
    })

if __name__ == '__main__':
    init_db()
    
    # Start continuous sensor reading in background
    sensor_thread = threading.Thread(target=continuous_sensor_reading, daemon=True)
    sensor_thread.start()
    
    print("🌱 NITK Air Quality Monitor Started")
    print(f"📊 Mode: {'Hardware' if HAS_SENSORS else 'Simulation'}")
    print("🌐 Access: http://0.0.0.0:5000")
    
    try:
        app.run(debug=False, host='0.0.0.0', port=5000)
    finally:
        if HAS_SENSORS:
            GPIO.cleanup()