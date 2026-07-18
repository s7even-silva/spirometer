// Definición del pin del sensor
const int pinSensor = A6;

// Intervalo de envío (no bloqueante, sin delay)
const unsigned long intervaloMs = 10;

// --- Parámetros de conversión ADC -> voltaje -> presión diferencial ---
const float VREF    = 5.0;     // voltaje de referencia del ADC (Nano = 5V)
const float ADC_MAX = 1023.0;  // resolución de 10 bits

// Cada sensor: 0.5V=0kPa, 4.5V=100kPa (0.04 V/kPa, offset 0.5V, se cancela al restar)
// Salida diferencial amplificada x10 por el opamp, sin offset adicional:
// V_out = 10 * 0.04 * dP = 0.4 * dP  ->  dP = V_out / 0.4 = 2.5 * V_out
const float PENDIENTE_M = 2.5; // kPa/V
const float OFFSET_B    = 0.0;

unsigned long siguienteMuestra = 0;

void setup() {
  Serial.begin(9600);
  delay(500); // da tiempo a que la app abra el puerto y limpie su búfer

  siguienteMuestra = millis();
}

void loop() {
  unsigned long ahora = millis();

  if ((long)(ahora - siguienteMuestra) >= 0) {
    int valorCrudo   = analogRead(pinSensor);
    float voltaje    = (valorCrudo / ADC_MAX) * VREF;
    float presionKpa = PENDIENTE_M * voltaje + OFFSET_B;
    float presionPa  = presionKpa * 1000.0; // la app (config.py/processing.py) trabaja en Pascales

    Serial.println(presionPa, 2); // una sola línea, un solo número: lo que espera serial_reader.py

    siguienteMuestra += intervaloMs;
  }
}