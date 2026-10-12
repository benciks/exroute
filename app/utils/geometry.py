import math

R_KM = 6371.0 

def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dlam = math.radians(lon2 - lon1)
  x = math.sin(dlam) * math.cos(phi2)
  y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
  return (math.degrees(math.atan2(x, y)) + 360) % 360

def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
  dlat = math.radians(b[0] - a[0])
  dlon = math.radians(b[1] - a[1])
  la1, la2 = math.radians(a[0]), math.radians(b[0])
  x = math.sin(dlat/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlon/2)**2
  return 2 * R_KM * math.asin(math.sqrt(x))