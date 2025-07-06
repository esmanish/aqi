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
        self.buffer_size = 8  # Increased for more stability
        
        # Realistic Mangalore baseline values (current conditions)
        self.base_values = {
            'pm25': 22,    # Current Mangalore PM2.5
            'pm10': 56,    # Current Mangalore PM10  
            'temp': 28,    # Typical Mangalore temperature
            'humidity': 65 # Typical coastal humidity
        }
        
        # For gradual changes and momentum
        self.current_values = {
            'pm25': self.base_values['pm25'],
            'pm10': self.base_values['pm10'],
            'temp': self.base_values['temp'],
            'humidity': self.base_values['humidity']
        }
        
        # Momentum factors for gradual changes
        self.momentum = 0.85  # How much previous value influences current (0.85 = 85% previous + 15% new)
        self.last_update = time.time()
        
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
            
            # Improved calibration for realistic Mangalore values
            # Baseline when no dust (clean air)
            pm25_baseline = 20  # Clean indoor air
            pm10_baseline = 45  # Clean indoor air
            
            # Convert sensor ratios to realistic concentrations
            # Higher ratio = more particles detected
            pm25 = pm25_baseline + (pm25_ratio * 150)  # Can go up to ~170 with dust
            pm10 = pm10_baseline + (pm10_ratio * 200)  # Can go up to ~245 with dust
            
            # Ensure PM10 >= PM2.5 (physically correct)
            if pm10 < pm25 * 1.2:
                pm10 = pm25 * 1.4
            
            # Apply momentum for gradual changes
            pm25 = self._apply_momentum('pm25', pm25)
            pm10 = self._apply_momentum('pm10', pm10)
            
            # Read environmental sensors with retry logic
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
            
            # Use gradual defaults if sensor fails
            if temp is None:
                temp = self._apply_momentum('temp', self.base_values['temp'] + random.uniform(-0.5, 0.5))
            else:
                temp = self._apply_momentum('temp', temp)
                
            if humidity is None:
                humidity = self._apply_momentum('humidity', self.base_values['humidity'] + random.uniform(-2, 2))
            else:
                humidity = self._apply_momentum('humidity', humidity)
            
            # Add to history for additional smoothing
            self.history['pm25'].append(pm25)
            self.history['pm10'].append(pm10)
            self.history['temp'].append(temp)
            self.history['humidity'].append(humidity)
            
            # Keep buffer size limited
            for key in self.history:
                if len(self.history[key]) > self.buffer_size:
                    self.history[key].pop(0)
            
            # Return smoothed averaged values
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
    
    def _apply_momentum(self, key, new_value):
        """Apply momentum to make changes gradual"""
        if key in self.current_values:
            # Gradual change: 85% previous + 15% new
            self.current_values[key] = (self.momentum * self.current_values[key] + 
                                      (1 - self.momentum) * new_value)
        else:
            self.current_values[key] = new_value
        
        return self.current_values[key]
    
    def _read_simulation(self):
        """Enhanced simulation with realistic Mangalore values and gradual changes"""
        current_time = time.time()
        time_since_last = current_time - self.last_update
        self.last_update = current_time
        
        # Very subtle daily patterns (much smaller variations)
        hour_of_day = (current_time % 86400) / 86400 * 24
        daily_pm_factor = 1.0 + 0.15 * math.sin(2 * math.pi * hour_of_day / 24 - math.pi/3)  # Small variation
        daily_temp_factor = 1.0 + 0.08 * math.sin(2 * math.pi * hour_of_day / 24)  # Small temp variation
        daily_humidity_factor = 1.0 - 0.12 * math.sin(2 * math.pi * hour_of_day / 24)  # Inverse humidity
        
        # Very slow location/environmental changes (every 10 minutes)
        location_seed = int(current_time / 600) % 5  # Changes every 10 minutes
        location_factor = 0.95 + (location_seed * 0.02)  # Very small variation (0.95 to 1.03)
        
        # Calculate target values with realistic Mangalore baseline
        target_pm25 = self.base_values['pm25'] * daily_pm_factor * location_factor
        target_pm10 = self.base_values['pm10'] * daily_pm_factor * location_factor
        target_temp = self.base_values['temp'] * daily_temp_factor
        target_humidity = self.base_values['humidity'] * daily_humidity_factor
        
        # Add very small random fluctuations
        target_pm25 += random.uniform(-0.8, 0.8)  # Reduced fluctuation
        target_pm10 += random.uniform(-1.2, 1.2)  # Reduced fluctuation
        target_temp += random.uniform(-0.3, 0.3)   # Reduced fluctuation
        target_humidity += random.uniform(-1.5, 1.5)  # Reduced fluctuation
        
        # Apply momentum for gradual changes
        pm25 = self._apply_momentum('pm25', target_pm25)
        pm10 = self._apply_momentum('pm10', target_pm10)
        temp = self._apply_momentum('temp', target_temp)
        humidity = self._apply_momentum('humidity', target_humidity)
        
        # Ensure realistic bounds for Mangalore
        pm25 = max(15, min(40, pm25))  # Realistic range for moderate air quality
        pm10 = max(max(pm25 * 1.8, 35), min(80, pm10))  # PM10 should be higher than PM2.5
        temp = max(24, min(35, temp))     # Mangalore temperature range
        humidity = max(50, min(85, humidity))  # Coastal humidity range
        
        # Add to history for additional smoothing
        self.history['pm25'].append(pm25)
        self.history['pm10'].append(pm10)
        self.history['temp'].append(temp)
        self.history['humidity'].append(humidity)
        
        # Keep buffer size limited
        for key in self.history:
            if len(self.history[key]) > self.buffer_size:
                self.history[key].pop(0)
        
        # Return smoothed values
        return {
            'pm25': round(sum(self.history['pm25']) / len(self.history['pm25']), 1),
            'pm10': round(sum(self.history['pm10']) / len(self.history['pm10']), 1),
            'temperature': round(sum(self.history['temp']) / len(self.history['temp']), 1),
            'humidity': round(sum(self.history['humidity']) / len(self.history['humidity']), 0),
            'timestamp': time.time()
        }
    
    def calculate_aqi(self, pm25, pm10):
        """EPA standard AQI calculation - this is correct"""
        aqi_pm25 = self._calc_aqi_pm25(pm25)
        aqi_pm10 = self._calc_aqi_pm10(pm10)
        return max(aqi_pm25, aqi_pm10)
    
    def _calc_aqi_pm25(self, pm25):
        """EPA PM2.5 AQI calculation"""
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
        """EPA PM10 AQI calculation"""
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
    
    def get_aqi_status(self, aqi):
        """Get AQI status description"""
        if aqi <= 50:
            return "Good"
        elif aqi <= 100:
            return "Moderate"
        elif aqi <= 150:
            return "Unhealthy for Sensitive Groups"
        elif aqi <= 200:
            return "Unhealthy"
        elif aqi <= 300:
            return "Very Unhealthy"
        else:
            return "Hazardous"