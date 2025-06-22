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

def setup_sensors():
    """Initialize hardware sensors if available"""
    global dht22
    if not HAS_SENSORS:
        print("📟 Hardware sensors not available - using simulation")
        return
    
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(18, GPIO.IN)  # PM2.5 sensor pin
        GPIO.setup(19, GPIO.IN)  # PM10 sensor pin
        dht22 = adafruit_dht.DHT22(board.D27)  # Temperature/Humidity sensor
        print("✅ Hardware sensors initialized successfully")
    except Exception as e:
        print(f"❌ Sensor setup failed: {e}")

def read_dust_sensor(pin, duration=3):
    """Read dust sensor data from GPIO pin"""
    if not HAS_SENSORS:
        # Simulation data with realistic patterns
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
    """Calculate Air Quality Index based on PM2.5 concentration (EPA standard)"""
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
    """Background thread for continuous sensor data collection"""
    global SENSOR_DATA
    setup_sensors()
    
    # Moving average buffers for data smoothing
    pm25_buffer = []
    pm10_buffer = []
    temp_buffer = []
    humidity_buffer = []
    buffer_size = 5
    
    print("🔄 Starting continuous sensor reading...")
    
    while True:
        try:
            if HAS_SENSORS and dht22:
                # Read DHT22 with retry mechanism
                temp = humidity = None
                for attempt in range(3):
                    try:
                        temp = dht22.temperature
                        humidity = dht22.humidity
                        if temp is not None and humidity is not None:
                            break
                        time.sleep(0.5)
                    except Exception as e:
                        if attempt == 2:
                            print(f"⚠️ DHT22 read failed: {e}")
                        time.sleep(0.5)
                
                # Read dust sensors
                pm25_ratio = read_dust_sensor(18, 3)
                pm10_ratio = read_dust_sensor(19, 3)
                pm25 = pm25_ratio * 0.1 * 10  # Convert to μg/m³
                pm10 = pm10_ratio * 0.1 * 12  # Convert to μg/m³
                
            else:
                # Enhanced simulation with realistic patterns
                current_time = time.time()
                
                # Daily patterns (higher pollution during day)
                hour_of_day = (current_time % 86400) / 3600  # Hours 0-24
                daily_factor = 1 + 0.3 * math.sin((hour_of_day - 6) * math.pi / 12)
                
                # Weekly patterns (lower on weekends)
                day_of_week = ((current_time / 86400) % 7)
                weekly_factor = 0.8 if day_of_week > 5 else 1.0
                
                # Base pollution levels with variation
                base_pm25 = 20 * daily_factor * weekly_factor
                pm25 = max(5, base_pm25 + random.uniform(-3, 3))
                pm10 = pm25 * 1.5 + random.uniform(-5, 5)
                
                # Temperature with daily cycle
                temp = 28 + 5 * math.sin((hour_of_day - 6) * math.pi / 12) + random.uniform(-1, 1)
                
                # Humidity inversely related to temperature
                humidity = max(30, min(90, 70 - (temp - 28) * 2 + random.uniform(-5, 5)))
            
            # Add to buffers for smoothing
            if pm25 is not None: pm25_buffer.append(max(0, pm25))
            if pm10 is not None: pm10_buffer.append(max(0, pm10))
            if temp is not None: temp_buffer.append(temp)
            if humidity is not None: humidity_buffer.append(max(0, min(100, humidity)))
            
            # Maintain buffer size
            for buffer in [pm25_buffer, pm10_buffer, temp_buffer, humidity_buffer]:
                if len(buffer) > buffer_size:
                    buffer.pop(0)
            
            # Calculate smoothed averages
            with SENSOR_LOCK:
                if pm25_buffer:
                    SENSOR_DATA['pm25'] = round(sum(pm25_buffer) / len(pm25_buffer), 1)
                if pm10_buffer:
                    SENSOR_DATA['pm10'] = round(sum(pm10_buffer) / len(pm10_buffer), 1)
                if temp_buffer:
                    SENSOR_DATA['temp'] = round(sum(temp_buffer) / len(temp_buffer), 1)
                if humidity_buffer:
                    SENSOR_DATA['humidity'] = round(sum(humidity_buffer) / len(humidity_buffer), 0)
                
                # Calculate AQI
                SENSOR_DATA['aqi'] = calculate_aqi(SENSOR_DATA['pm25'])
            
            # Update every 5 seconds
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ Sensor reading error: {e}")
            time.sleep(5)

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
    
    # Return 404 for missing tiles
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
    """Collect and store air quality data at specified location with time-series data"""
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        req = request.json
        required_fields = ['locationName', 'latitude', 'longitude']
        
        if not all(field in req for field in required_fields):
            return jsonify({'error': f'Missing required fields: {required_fields}'}), 400
        
        # Check if this is a data point submission or final collection
        if 'collectionData' in req:
            return save_complete_collection(req)
        else:
            return save_simple_collection(req)
            
    except Exception as e:
        print(f"❌ Collection error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def save_simple_collection(req):
    """Save a simple collection (current approach)"""
    try:
        # Validate and parse coordinates
        lat = float(req['latitude'])
        lng = float(req['longitude'])
        
        # Validate coordinates are within NITK campus bounds
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
        
        print(f"✅ Simple collection saved: ID={reading_id}, Location='{location_name}'")
        
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
        # Validate and parse coordinates
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
        avg_aqi = calculate_aqi(avg_pm25)
        
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
        
        print(f"✅ Complete collection saved: ID={reading_id}, Points={len(collection_data)}")
        
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
        
        # Get all readings with collection data info
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
        
        # Get collection data points
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

@app.route('/api/readings/<int:reading_id>', methods=['DELETE'])
def delete_reading(reading_id):
    """Delete a specific reading and all its collection data"""
    try:
        conn = sqlite3.connect('data/air_quality.db')
        cursor = conn.cursor()
        
        # Check if reading exists
        cursor.execute('SELECT location_name FROM readings WHERE id = ?', (reading_id,))
        reading = cursor.fetchone()
        
        if not reading:
            conn.close()
            return jsonify({'error': 'Reading not found'}), 404
        
        location_name = reading[0]
        
        # Delete collection data first (foreign key constraint)
        cursor.execute('DELETE FROM collection_data WHERE reading_id = ?', (reading_id,))
        collection_deleted = cursor.rowcount
        
        # Delete the main reading
        cursor.execute('DELETE FROM readings WHERE id = ?', (reading_id,))
        reading_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if reading_deleted > 0:
            print(f"✅ Deleted reading ID={reading_id}, Location='{location_name}', Collection points={collection_deleted}")
            return jsonify({
                'id': reading_id,
                'location': location_name,
                'collection_points_deleted': collection_deleted,
                'status': 'success',
                'message': f'Successfully deleted reading from {location_name}'
            })
        else:
            return jsonify({'error': 'Failed to delete reading'}), 500
            
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/status')
def system_status():
    """Get system status and health information"""
    try:
        # Check database
        conn = sqlite3.connect('data/air_quality.db')
        reading_count = conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
        collection_points = conn.execute('SELECT COUNT(*) FROM collection_data').fetchone()[0]
        latest_reading = conn.execute('SELECT created_at FROM readings ORDER BY created_at DESC LIMIT 1').fetchone()
        conn.close()
        
        # Check sensor status
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
        # Count available tiles
        tile_count = 0
        tiles_path = 'static/tiles'
        
        if os.path.exists(tiles_path):
            for root, dirs, files in os.walk(tiles_path):
                tile_count += sum(1 for f in files if f.endswith('.png'))
        
        # Check metadata
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
    print("🌱 NITK Air Quality Monitor Starting...")
    
    # Initialize database
    init_db()
    
    # Start continuous sensor reading in background
    sensor_thread = threading.Thread(target=continuous_sensor_reading, daemon=True)
    sensor_thread.start()
    
    print("📊 Mode: Hardware" if HAS_SENSORS else "📊 Mode: Simulation")
    print("🌐 Server: http://0.0.0.0:5000")
    print("📱 Dashboard: http://localhost:5000")
    print("🔗 API Status: http://localhost:5000/api/status")
    print("📈 Readings API: http://localhost:5000/api/readings")
    print("\n✅ System ready! Press Ctrl+C to stop.\n")
    
    try:
        # Run Flask application
        app.run(
            debug=False,  # Set to True for development
            host='0.0.0.0', 
            port=5000,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Shutting down NITK Air Quality Monitor...")
    finally:
        # Cleanup GPIO if using hardware
        if HAS_SENSORS:
            try:
                GPIO.cleanup()
                print("✅ GPIO cleanup completed")
            except:
                pass
        print("👋 Goodbye!")