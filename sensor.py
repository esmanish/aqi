import random, time, math

# Try hardware imports
try:
    import RPi.GPIO as GPIO
    import board
    import adafruit_dht
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False

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
        if self.hardware and HAS_HARDWARE:
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
        if self.hardware and HAS_HARDWARE:
            return self._read_hardware()
        else:
            return self._read_simulation()
    
    def read_dust_sensor(self, pin, duration=3):
        """Read dust sensor with proper timing"""
        if not HAS_HARDWARE:
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
            pm25 = max(8, pm25_ratio * 100 + 15)  # 15-30 range
            pm10 = max(pm25 * 1.5, pm10_ratio * 120 + 35)  # 35-60 range
            
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