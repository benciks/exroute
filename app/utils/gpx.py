from xml.sax.saxutils import escape

from app.utils.polyline import decode_shape

def to_gpx(name: str, polyline: str, waypoints: list[dict]) -> str:
  wpts = "".join(
    f'  <wpt lat="{w["lat"]}" lon="{w["lon"]}">\n    <name>{escape(w["name"])}</name>\n  </wpt>\n'
    for w in waypoints
  )
  trkpts = "\n".join(
    f'      <trkpt lat="{lat}" lon="{lon}"/>'
    for lat, lon in decode_shape(polyline)
  )

  return f'''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="exroute" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>{escape(name)}</name>
  </metadata>
{wpts}  <trk>
    <name>{escape(name)}</name>
    <trkseg>
{trkpts}
    </trkseg>
  </trk>
</gpx>
'''
