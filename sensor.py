import random, time, math

class SensorManager:
    def __init__(self, hardware=False):
        self.hardware = hardware
        self.history = {'pm25': [], 'pm10': [], 'temp': [], 'humidity': []}
        self.buffer_size = 5
        self.base_values = {
            'pm25': 20, 'pm10': 30, 'temp': 28, 'humidity': 65
        }
        
    def read_sensors(self):
        if self.hardware:
            return self._read_hardware()
        else:
            return self._read_simulation()
    
    def _read_simulation(self):
        # Create stable readings with realistic patterns
        t = time.time()
        
        # Daily patterns
        hour_factor = math.sin((t % 86400) / 86400 * 2 * math.pi - math.pi/2)
        
        # Base values with time-based variation
        pm25 = self.base_values['pm25'] + 10 * hour_factor + random.uniform(-1, 1)
        pm10 = self.base_values['pm10'] + 15 * hour_factor + random.uniform(-1.5, 1.5)
        temp = self.base_values['temp'] + 4 * hour_factor + random.uniform(-0.3, 0.3)
        humidity = self.base_values['humidity'] - 10 * hour_factor + random.uniform(-1, 1)
        
        # Add to history for smoothing
        self.history['pm25'].append(max(5, pm25))
        self.history['pm10'].append(max(10, pm10))
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
    
    def _read_hardware(self):
        # Implement actual hardware reading here
        # This is a placeholder that returns stable values
        return self._read_simulation()
    
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