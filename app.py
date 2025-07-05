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

# Import sensor manager inline to avoid import issues
class SensorManager:
    def __init__(self, hardware=False):
        self.hardware = hardware
        self.history = {'pm25': [], 'pm10': [], 'temp': [], 'humidity': []}
        self.buffer_size = 5
        
        # Base values for Mangalore region
        self.base_values = {
            'pm25': 18, 'pm10': 42, 'temp': 28, 'humidity': 65
        }
        
        # Initialize hardware sensors
        if self.hardware and HAS_SENSORS:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # PM2.5
                GPIO.setup(24, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # PM10
                self.dht22 = adafruit_dht.DHT22(board.D27)
                print("✅ Hardware sensors initialized (GPIO 23/24)")
            except Exception as e:
                print(f"❌ Hardware init failed: {e}")
                self.hardware = False
    
    def read_sensors(self):
        if self.hardware and HAS_SENSORS:
            return self._read_hardware()
        else:
            return self._read_simulation()
    
    def read_dust_sensor(self, pin, duration=3):
        """Read dust sensor with proper timing"""
        if not HAS_SENSORS:
            return random.uniform(0.01, 0.3)
        
        start_time = time.time()
        low_time = 0
        
        while (time.time() - start_time) < duration:
            if GPIO.input(pin) == GPIO.LOW:
                low_time += 0.01
            time.sleep(0.01)
        
        ratio = (low_time / duration) * 100
        return max(0, ratio)
    
    def _read_hardware(self):
        try:
            # Read dust sensors
            pm25_ratio = self.read_dust_sensor(23, 3)
            pm10_ratio = self.read_dust_sensor(24, 3)
            
            # Convert ratios to concentrations for Mangalore
            pm25 = max(8, pm25_ratio * 100)  # 15-30 range
            pm10 = max(pm25 * 1.5, pm10_ratio * 120)  # 35-60 range
            
            # Read environmental sensors
            temp = humidity = None
            for attempt in range(3):
                try:
                    temp = self.dht22.temperature
                    humidity = self.dht22.humidity
                    if temp is not None and humidity is not None:
                        break
                except:
                    pass
                time.sleep(0.3)
            
            # Use defaults if sensor fails
            if temp is None:
                temp = self.base_values['temp'] + random.uniform(-1, 1)
            if humidity is None:
                humidity = self.base_values['humidity'] + random.uniform(-3, 3)
            
            # Add to history
            self.history['pm25'].append(pm25)
            self.history['pm10'].append(pm10)
            self.history['temp'].append(temp)
            self.history['humidity'].append(humidity)
            
            # Keep buffer size limited
            for key in self.history:
                if len(self.history[key]) > self.buffer_size:
                    self.history[key].pop(0)
            
            # Return averaged values
            return {
                'pm25': round(sum(self.history['pm25']) / len(self.history['pm25']), 1),
                'pm10': round(sum(self.history['pm10']) / len(self.history['pm10']), 1),
                'temperature': round(sum(self.history['temp']) / len(self.history['temp']), 1),
                'humidity': round(sum(self.history['humidity']) / len(self.history['humidity']), 0),
                'timestamp': time.time()
            }
            
        except Exception as e:
            print(f"❌ Hardware reading error: {e}")
            return self._read_simulation()
    
    def _read_simulation(self):
        # Enhanced simulation with location variation
        t = time.time()
        
        # Daily patterns
        hour_factor = math.sin((t % 86400) / 86400 * 2 * math.pi - math.pi/2)
        
        # Location-based variation (changes every 5 minutes)
        location_seed = int(t / 300) % 7
        location_factor = 0.8 + (location_seed * 0.06)  # 0.8 to 1.16 multiplier
        
        pm25 = self.base_values['pm25'] * location_factor + 3 * hour_factor + random.uniform(-2, 2)
        pm10 = self.base_values['pm10'] * location_factor + 5 * hour_factor + random.uniform(-3, 3)
        temp = self.base_values['temp'] + 4 * hour_factor + random.uniform(-0.8, 0.8)
        humidity = self.base_values['humidity'] - 8 * hour_factor + random.uniform(-4, 4)
        
        # Realistic bounds for Mangalore
        pm25 = max(12, min(28, pm25))
        pm10 = max(max(pm25 * 1.6, 30), min(55, pm10))
        temp = max(18, min(38, temp))
        humidity = max(35, min(85, humidity))
        
        # Add to history for smoothing
        self.history['pm25'].append(pm25)
        self.history['pm10'].append(pm10)
        self.history['temp'].append(temp)
        self.history['humidity'].append(humidity)
        
        # Keep buffer size limited
        for key in self.history:
            if len(self.history[key]) > self.buffer_size:
                self.history[key].pop(0)
        
        # Return averaged values
        return {
            'pm25': round(sum(self.history['pm25']) / len(self.history['pm25']), 1),
            'pm10': round(sum(self.history['pm10']) / len(self.history['pm10']), 1),
            'temperature': round(sum(self.history['temp']) / len(self.history['temp']), 1),
            'humidity': round(sum(self.history['humidity']) / len(self.history['humidity']), 0),
            'timestamp': time.time()
        }
    
    def calculate_aqi(self, pm25, pm10):
        # EPA standard AQI calculation
        aqi_pm25 = self._calc_aqi_pm25(pm25)
        aqi_pm10 = self._calc_aqi_pm10(pm10)
        return max(aqi_pm25, aqi_pm10)
    
    def _calc_aqi_pm25(self, pm25):
        if pm25 <= 12.0:
            return round((50/12.0) * pm25)
        elif pm25 <= 35.4:
            return round(50 + ((100-50)/(35.4-12.0)) * (pm25-12.0))
        elif pm25 <= 55.4:
            return round(100 + ((150-100)/(55.4-35.4)) * (pm25-35.4))
        elif pm25 <= 150.4:
            return round(150 + ((200-150)/(150.4-55.4)) * (pm25-55.4))
        elif pm25 <= 250.4:
            return round(200 + ((300-200)/(250.4-150.4)) * (pm25-150.4))
        else:
            return min(round(300 + ((500-300)/(500.4-250.4)) * (pm25-250.4)), 500)
    
    def _calc_aqi_pm10(self, pm10):
        if pm10 <= 54:
            return round((50/54) * pm10)
        elif pm10 <= 154:
            return round(50 + ((100-50)/(154-54)) * (pm10-54))
        elif pm10 <= 254:
            return round(100 + ((150-100)/(254-154)) * (pm10-154))
        elif pm10 <= 354:
            return round(150 + ((200-150)/(354-254)) * (pm10-254))
        elif pm10 <= 424:
            return round(200 + ((300-200)/(424-354)) * (pm10-354))
        else:
            return 301

# Global sensor manager
sensor_manager = None

def init_db():
    """Initialize the SQLite database with proper schema"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect('data/air_quality.db')
    
    # Create main readings table
    conn.execute('''CREATE TABLE IF NOT EXISTS readings
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     location_name TEXT NOT NULL, 
                     latitude REAL NOT NULL, 
                     longitude REAL NOT NULL,
                     aqi INTEGER NOT NULL, 
                     pm25 REAL NOT NULL, 
                     pm10 REAL NOT NULL, 
                     temp REAL NOT NULL, 
                     humidity REAL NOT NULL,
                     timestamp REAL NOT NULL,
                     created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Create collection data points table for time-series data
    conn.execute('''CREATE TABLE IF NOT EXISTS collection_data
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     reading_id INTEGER NOT NULL,
                     pm25 REAL NOT NULL,
                     pm10 REAL NOT NULL,
                     temperature REAL NOT NULL,
                     humidity REAL NOT NULL,
                     timestamp REAL NOT NULL,
                     sequence_number INTEGER NOT NULL,
                     FOREIGN KEY (reading_id) REFERENCES readings (id))''')
    
    # Create indexes for better performance
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)''')
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_location ON readings(location_name)''')
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_reading_id ON collection_data(reading_id)''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")

def continuous_sensor_reading():
    """Background thread for continuous sensor data collection"""
    global SENSOR_DATA, sensor_manager
    
    # Initialize sensor manager
    sensor_manager = SensorManager(hardware=HAS_SENSORS)
    
    print("🔄 Starting continuous sensor reading...")
    print("📊 Mode: Hardware" if HAS_SENSORS else "📊 Mode: Simulation")
    
    while True:
        try:
            # Get sensor data
            data = sensor_manager.read_sensors()
            
            with SENSOR_LOCK:
                SENSOR_DATA['pm25'] = data['pm25']
                SENSOR_DATA['pm10'] = data['pm10']
                SENSOR_DATA['temp'] = data['temperature']
                SENSOR_DATA['humidity'] = data['humidity']
                SENSOR_DATA['aqi'] = sensor_manager.calculate_aqi(data['pm25'], data['pm10'])
            
            # Print readings for debugging
            print(f"📊 PM2.5: {data['pm25']:.1f}, PM10: {data['pm10']:.1f}, AQI: {SENSOR_DATA['aqi']}")
            
            # Update every 10 seconds
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ Sensor reading error: {e}")
            time.sleep(10)

@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('dashboard.html')

@app.route('/tiles/<int:z>/<int:x>/<int:y>.png')
def serve_tile(z, x, y):
    """Serve offline map tiles"""
    tile_path = f'static/tiles/{z}/{x}/{y}.png'
    
    if os.path.exists(tile_path) and is_tile_in_bounds(x, y, z):
        return send_file(tile_path, mimetype='image/png')
    
    return '', 404

def is_tile_in_bounds(x, y, z):
    """Check if tile coordinates are within NITK campus bounds"""
    n = 2.0 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    
    return not (lon_max < BOUNDS['west'] or lon_min > BOUNDS['east'] or 
                lat_max < BOUNDS['south'] or lat_min > BOUNDS['north'])

@app.route('/api/realtime')
def realtime_data():
    """Get current real-time sensor data"""
    with SENSOR_LOCK:
        data = SENSOR_DATA.copy()
    
    return jsonify({
        'pm25': data['pm25'],
        'pm10': data['pm10'],
        'temperature': data['temp'],
        'humidity': data['humidity'],
        'aqi': data['aqi'],
        'timestamp': datetime.now().isoformat(),
        'status': 'active'
    })

@app.route('/api/collect', methods=['POST'])
def collect_data():
    """Collect and store air quality data at specified location"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        req = request.json
        required_fields = ['locationName', 'latitude', 'longitude']
        
        if not all(field in req for field in required_fields):
            return jsonify({'error': f'Missing required fields: {required_fields}'}), 400
        
        if 'collectionData' in req:
            return save_complete_collection(req)
        else:
            return save_simple_collection(req)
            
    except Exception as e:
        print(f"❌ Collection error: {e}")
        return jsonify({'error': str(e)}), 500

def save_simple_collection(req):
    """Save a simple collection"""
    try:
        lat = float(req['latitude'])
        lng = float(req['longitude'])
        
        if not (BOUNDS['south'] <= lat <= BOUNDS['north'] and 
                BOUNDS['west'] <= lng <= BOUNDS['east']):
            return jsonify({
                'error': 'Coordinates outside NITK campus bounds',
                'bounds': BOUNDS
            }), 400
        
        location_name = req['locationName'].strip()
        
        # Get current sensor data
        with SENSOR_LOCK:
            current_data = SENSOR_DATA.copy()
        
        # Store in database
        conn = sqlite3.connect('data/air_quality.db')
        cursor = conn.cursor()
        
        cursor.execute('''INSERT INTO readings 
                         (location_name, latitude, longitude, aqi, pm25, pm10, temp, humidity, timestamp)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (location_name, lat, lng, current_data['aqi'],
                       current_data['pm25'], current_data['pm10'], 
                       current_data['temp'], current_data['humidity'], time.time()))
        
        reading_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Data collected successfully: {location_name} at ({lat}, {lng}), ID: {reading_id}")
        
        return jsonify({
            'id': reading_id,
            'aqi': current_data['aqi'],
            'pm25': current_data['pm25'],
            'pm10': current_data['pm10'],
            'temperature': current_data['temp'],
            'humidity': current_data['humidity'],
            'timestamp': datetime.now().isoformat(),
            'location': location_name,
            'latitude': lat,
            'longitude': lng,
            'status': 'success'
        })
        
    except Exception as e:
        print(f"❌ Simple collection error: {e}")
        return jsonify({'error': str(e)}), 500

def save_complete_collection(req):
    """Save a complete collection with time-series data"""
    try:
        lat = float(req['latitude'])
        lng = float(req['longitude'])
        location_name = req['locationName'].strip()
        collection_data = req['collectionData']
        
        if not collection_data or len(collection_data) == 0:
            return save_simple_collection(req)
        
        # Calculate averages from collection data
        avg_pm25 = sum(d['pm25'] for d in collection_data) / len(collection_data)
        avg_pm10 = sum(d['pm10'] for d in collection_data) / len(collection_data)
        avg_temp = sum(d['temperature'] for d in collection_data) / len(collection_data)
        avg_humidity = sum(d['humidity'] for d in collection_data) / len(collection_data)
        
        # Calculate AQI
        avg_aqi = sensor_manager.calculate_aqi(avg_pm25, avg_pm10) if sensor_manager else 50
        
        conn = sqlite3.connect('data/air_quality.db')
        cursor = conn.cursor()
        
        # Insert main reading record
        cursor.execute('''INSERT INTO readings 
                         (location_name, latitude, longitude, aqi, pm25, pm10, temp, humidity, timestamp)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (location_name, lat, lng, avg_aqi, avg_pm25, avg_pm10, 
                       avg_temp, avg_humidity, time.time()))
        
        reading_id = cursor.lastrowid
        
        # Insert individual collection data points
        for i, data_point in enumerate(collection_data):
            cursor.execute('''INSERT INTO collection_data
                             (reading_id, pm25, pm10, temperature, humidity, timestamp, sequence_number)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (reading_id, data_point['pm25'], data_point['pm10'],
                           data_point['temperature'], data_point['humidity'],
                           data_point.get('timestamp', time.time()), i))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Data collected successfully: {location_name} at ({lat}, {lng}), ID: {reading_id}")
        
        return jsonify({
            'id': reading_id,
            'aqi': avg_aqi,
            'pm25': avg_pm25,
            'pm10': avg_pm10,
            'temperature': avg_temp,
            'humidity': avg_humidity,
            'timestamp': datetime.now().isoformat(),
            'location': location_name,
            'latitude': lat,
            'longitude': lng,
            'collection_points': len(collection_data),
            'status': 'success'
        })
        
    except Exception as e:
        print(f"❌ Complete collection error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/readings')
def get_readings():
    """Get all stored air quality readings"""
    try:
        conn = sqlite3.connect('data/air_quality.db')
        cursor = conn.cursor()
        
        cursor.execute('''SELECT r.id, r.location_name, r.latitude, r.longitude, r.aqi, r.pm25, r.pm10, 
                                 r.temp, r.humidity, r.timestamp, r.created_at,
                                 COUNT(c.id) as collection_points
                         FROM readings r
                         LEFT JOIN collection_data c ON r.id = c.reading_id
                         GROUP BY r.id
                         ORDER BY r.created_at DESC''')
        
        readings = []
        for row in cursor.fetchall():
            readings.append({
                'id': row[0],
                'location_name': row[1],
                'latitude': row[2],
                'longitude': row[3],
                'aqi': row[4],
                'pm25': row[5],
                'pm10': row[6],
                'temp': row[7],
                'humidity': row[8],
                'timestamp': row[9],
                'created_at': row[10],
                'has_collection_data': row[11] > 0,
                'collection_points': row[11]
            })
        
        conn.close()
        
        print(f"📊 Retrieved {len(readings)} readings from database")
        
        return jsonify({
            'readings': readings,
            'count': len(readings),
            'status': 'success'
        })
        
    except Exception as e:
        print(f"❌ Error retrieving readings: {e}")
        return jsonify({'error': 'Failed to retrieve readings', 'readings': []}), 500

@app.route('/api/readings/<int:reading_id>/collection-data')
def get_collection_data(reading_id):
    """Get collection time-series data for a specific reading"""
    try:
        conn = sqlite3.connect('data/air_quality.db')
        cursor = conn.cursor()
        
        cursor.execute('''SELECT pm25, pm10, temperature, humidity, timestamp, sequence_number
                         FROM collection_data 
                         WHERE reading_id = ? 
                         ORDER BY sequence_number''', (reading_id,))
        
        collection_points = []
        for row in cursor.fetchall():
            collection_points.append({
                'pm25': row[0],
                'pm10': row[1],
                'temperature': row[2],
                'humidity': row[3],
                'timestamp': row[4],
                'sequence': row[5]
            })
        
        conn.close()
        
        return jsonify({
            'reading_id': reading_id,
            'collection_data': collection_points,
            'count': len(collection_points),
            'status': 'success'
        })
        
    except Exception as e:
        print(f"❌ Error retrieving collection data: {e}")
        return jsonify({'error': 'Failed to retrieve collection data', 'collection_data': []}), 500

@app.route('/api/status')
def system_status():
    """Get system status and health information"""
    try:
        conn = sqlite3.connect('data/air_quality.db')
        reading_count = conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
        collection_points = conn.execute('SELECT COUNT(*) FROM collection_data').fetchone()[0]
        latest_reading = conn.execute('SELECT created_at FROM readings ORDER BY created_at DESC LIMIT 1').fetchone()
        conn.close()
        
        with SENSOR_LOCK:
            sensor_status = 'active' if any(SENSOR_DATA.values()) else 'initializing'
            latest_values = SENSOR_DATA.copy()
        
        return jsonify({
            'sensors': 'hardware' if HAS_SENSORS else 'simulation',
            'database': 'connected',
            'reading_count': reading_count,
            'collection_points': collection_points,
            'latest_reading': latest_reading[0] if latest_reading else None,
            'sensor_status': sensor_status,
            'current_values': latest_values,
            'bounds': BOUNDS,
            'uptime': time.time(),
            'status': 'healthy'
        })
        
    except Exception as e:
        print(f"❌ Status check error: {e}")
        return jsonify({
            'sensors': 'hardware' if HAS_SENSORS else 'simulation',
            'database': 'error',
            'reading_count': 0,
            'sensor_status': 'error',
            'error': str(e),
            'status': 'degraded'
        }), 500

@app.route('/api/map-status')
def map_status():
    """Get offline map tile availability status"""
    try:
        tile_count = 0
        tiles_path = 'static/tiles'
        
        if os.path.exists(tiles_path):
            for root, dirs, files in os.walk(tiles_path):
                tile_count += sum(1 for f in files if f.endswith('.png'))
        
        metadata_path = 'static/tiles/metadata.json'
        metadata = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        
        return jsonify({
            'ready': tile_count > 0,
            'available_tiles': tile_count,
            'metadata': metadata,
            'progress': {
                'downloaded': tile_count,
                'total': metadata.get('total', tile_count),
                'percentage': 100 if tile_count > 0 else 0
            },
            'bounds': BOUNDS
        })
        
    except Exception as e:
        print(f"❌ Map status error: {e}")
        return jsonify({
            'ready': False,
            'available_tiles': 0,
            'progress': {'downloaded': 0, 'total': 0, 'percentage': 0},
            'error': str(e)
        })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    print("🌱 NITK Air Quality Monitor Started")
    
    # Initialize database
    init_db()
    
    # Start continuous sensor reading in background
    sensor_thread = threading.Thread(target=continuous_sensor_reading, daemon=True)
    sensor_thread.start()
    
    print("📊 Mode: Hardware" if HAS_SENSORS else "📊 Mode: Simulation")
    print("🌐 Access: http://0.0.0.0:5000")
    print("✅ System ready! Press Ctrl+C to stop.\n")
    
    try:
        app.run(
            debug=False,
            host='0.0.0.0', 
            port=5000,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Shutdown signal received")
        print("🔄 Sensor manager stopped")
    finally:
        if HAS_SENSORS:
            try:
                print("🧹 GPIO cleaned up")
                GPIO.cleanup()
            except:
                pass
        print("👋 Goodbye!")