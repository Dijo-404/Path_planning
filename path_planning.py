import xml.etree.ElementTree as ET
import argparse
from shapely.geometry import Polygon, LineString
from shapely.ops import transform as shapely_transform
import pyproj

##################################################################################################
def parse_kml_polygon(kml_file):
    """
    Parse the first Polygon in a KML file and return a list of (lon, lat) tuples.
    """
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    tree = ET.parse(kml_file)
    root = tree.getroot()
    polygon_elem = root.find('.//kml:Polygon', ns)
    if polygon_elem is None:
        raise ValueError("No Polygon found in KML file.")
    coords_elem = polygon_elem.find('.//kml:coordinates', ns)
    if coords_elem is None or not coords_elem.text.strip():
        raise ValueError("No coordinates found in Polygon.")
    coords_text = coords_elem.text.strip()
    coord_list = []
    for coord_str in coords_text.split():
        parts = coord_str.split(',')
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        coord_list.append((lon, lat))
    if len(coord_list) < 3:
        raise ValueError("Polygon must have at least 3 coordinates.")
    return coord_list
##################################################################################################
def get_utm_crs(lat, lon):
    """
    Return appropriate UTM CRS string for a given latitude and longitude.
    """
    zone_number = int((lon + 180) / 6) + 1
    if lat >= 0:
        return f"EPSG:{32600 + zone_number}"
    else:
        return f"EPSG:{32700 + zone_number}"
##################################################################################################
def generate_sweep_waypoints(polygon_coords, spacing, waypoint_interval, altitude):
    """
    Generate a horizontal sweep (lawnmower) pattern within the polygon.
    spacing: distance between sweep lines in meters
    waypoint_interval: distance between waypoints along each sweep line in meters
    altitude: flight altitude in meters
    Returns a list of (lon, lat, alt) tuples for the waypoints.
    """
    poly_lonlat = Polygon(polygon_coords)
    if not poly_lonlat.is_valid or poly_lonlat.is_empty:
        raise ValueError("Invalid polygon geometry.")
    centroid = poly_lonlat.centroid
    utm_crs = get_utm_crs(centroid.y, centroid.x)
    project_to_utm = pyproj.Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True).transform
    project_to_latlon = pyproj.Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True).transform
    poly_utm = shapely_transform(project_to_utm, poly_lonlat)
    minx, miny, maxx, maxy = poly_utm.bounds
    y = miny
    lines = []
    while y <= maxy:
        line = LineString([(minx, y), (maxx, y)])
        segment = line.intersection(poly_utm)
        if not segment.is_empty:
            if segment.geom_type == 'LineString':
                lines.append(segment)
            elif segment.geom_type == 'MultiLineString':
                for seg in segment:
                    lines.append(seg)
        y += spacing
    lines = sorted(lines, key=lambda l: l.centroid.y)
    waypoints = []
    reverse = False
    for line in lines:
        length = line.length
        num_points = max(int(length // waypoint_interval) + 1, 2)
        segment_points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            pt = line.interpolate(t * length)
            lon, lat = project_to_latlon(pt.x, pt.y)
            segment_points.append((lon, lat, altitude))
        if reverse:
            segment_points.reverse()
        waypoints.extend(segment_points)
        reverse = not reverse
    return waypoints
##################################################################################################
def write_kml_waypoints(output_file, waypoints):
    """
    Write waypoints to a KML file as a single LineString.
    """
    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace('', kml_ns)
    kml_elem = ET.Element(f"{{{kml_ns}}}kml")
    doc_elem = ET.SubElement(kml_elem, "Document")
    placemark = ET.SubElement(doc_elem, "Placemark")
    name = ET.SubElement(placemark, "name")
    name.text = "Generated Flight Path"
    ls = ET.SubElement(placemark, "LineString")
    tessellate = ET.SubElement(ls, "tessellate")
    tessellate.text = "1"
    altitudeMode = ET.SubElement(ls, "altitudeMode")
    altitudeMode.text = "relativeToGround"
    coords_elem = ET.SubElement(ls, "coordinates")
    coords_text = " ".join(f"{lon},{lat},{alt}" for lon, lat, alt in waypoints)
    coords_elem.text = coords_text
    tree = ET.ElementTree(kml_elem)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"KML flight path written to {output_file}")
##################################################################################################
def main():
    parser = argparse.ArgumentParser(description="Generate horizontal sweep flight path from KML polygon.")
    parser.add_argument("input_kml", help="Input KML file containing a Polygon definition")
    parser.add_argument("output_kml", help="Output KML file for the generated flight path")
    parser.add_argument("--spacing", type=float, default=7.0, help="Spacing between sweep lines in meters (default: 20)")
    parser.add_argument("--waypoint_interval", type=float, default=10.0, help="Distance between waypoints along sweep line in meters (default: 10)")
    parser.add_argument("--altitude", type=float, default=20.0, help="Flight altitude in meters (default: 50)")
    args = parser.parse_args()
    polygon_coords = parse_kml_polygon(args.input_kml)
    waypoints = generate_sweep_waypoints(polygon_coords, args.spacing, args.waypoint_interval, args.altitude)
    write_kml_waypoints(args.output_kml, waypoints)
##################################################################################################
if __name__ == "__main__":
    main()
