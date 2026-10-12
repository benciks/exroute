from polyline import decode as _decode, encode as _encode

# Helpers to use a proper precision 6 needed by valhalla instead of the default 5
def decode_shape(s: str) -> list[tuple[float, float]]:
    return _decode(s, precision=6)

def encode_shape(points: list[tuple[float, float]]) -> str:
    return _encode(points, precision=6)

def join_legs(shapes: list[str]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i, s in enumerate(shapes):
        leg = _decode(s, precision=6)
        out.extend(leg if i == 0 else leg[1:])   # drop seam point between legs
    return out