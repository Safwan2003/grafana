import os, time, math, random, datetime
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

URL    = os.getenv("INFLUX_URL", "") 
TOKEN  = os.getenv("INFLUX_TOKEN", "")
ORG    = os.getenv("INFLUX_ORG", "")
BUCKET = os.getenv("INFLUX_BUCKET", "energy_lab")

SITE   = os.getenv("SITE", "shu")
SENSOR = os.getenv("SENSOR", "sim_pi01")

if not (URL and TOKEN and ORG and BUCKET):
    raise SystemExit("Set INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET in .env")

client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS) 

acc_kwh = 0.0

def noisy(val, pct=0.005):
    import random
    return val * (1.0 + random.uniform(-pct, pct))

def day_pattern():
    now = datetime.datetime.now()
    h = now.hour + now.minute/60
    base = 0.35 + 0.35 * math.exp(-((h-19)/3.5)**2) + 0.15 * math.exp(-((h-12)/4.0)**2)
    return min(1.0, max(0.1, base))

def appliance_spike():
    import random
    return random.random() < 0.06

def simulate_vrms():
    drift = 4.0 * math.sin(time.time()/400.0)
    return noisy(230.0 + drift, pct=0.003)

def simulate_irms():
    base = 0.8 + 10.0 * day_pattern()
    if appliance_spike():
        import random
        base += random.uniform(4.0, 12.0)
    return noisy(base, pct=0.02)

def simulate_pf():
    base = 0.82 + 0.1 * day_pattern()
    return min(0.98, max(0.75, noisy(base, pct=0.02)))

print("Streaming simulated data → InfluxDB Cloud 2. Ctrl+C to stop.\n")
try:
    while True:
        vrms = simulate_vrms() # Voltage
        irms = simulate_irms() # Current
        pf = simulate_pf() # Power Factor
        s_apparent = vrms * irms
        p_real = s_apparent * pf
        acc_kwh += max(p_real, 0.0) * 1.0 / 3.6e6

        v_peak = vrms * math.sqrt(2.0)
        i_peak = irms * math.sqrt(2.0)

        point = (Point("power_samples")
                 .tag("site", SITE).tag("sensor", SENSOR)
                 .field("vrms", float(vrms)).field("irms", float(irms))
                 .field("p_real", float(p_real)).field("s_apparent", float(s_apparent))
                 .field("pf", float(pf)).field("energy_kwh", float(acc_kwh))
                 .field("v_peak", float(v_peak)).field("i_peak", float(i_peak)))

        write_api.write(bucket=BUCKET, record=point, write_precision=WritePrecision.S)

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] wrote p={p_real:.1f}W  vrms={vrms:.1f}V  irms={irms:.2f}A  pf={pf:.2f}  energy={acc_kwh:.4f}kWh")
        time.sleep(1.0)
except KeyboardInterrupt:
    print("\nStopped.")
