"""Parse and extract chart data from Word documents."""

import re
import json
from pathlib import Path
from docx import Document
from typing import Dict, List, Any, Optional
from lxml import etree


def extract_charts_from_docx(docx_path: str) -> List[Dict[str, Any]]:
    """Extract all native Word charts from document."""
    try:
        doc = Document(docx_path)
        charts = []
        chart_count = 0

        print("📊 Extracting native charts from relationships...")

        # Extract native charts only
        for rel_id, rel in doc.part.rels.items():
            if "chart" in rel.target_ref:
                print(f"  Attempting {rel_id}...", end=" ")
                try:
                    chart_part = rel.target_part
                    chart_xml = chart_part.blob

                    # Parse the chart
                    chart_data = parse_chart_xml(chart_xml, rel_id=rel_id)
                    if chart_data:
                        charts.append(chart_data)
                        chart_count += 1
                        print(f"✓ {chart_data.get('title', 'Unknown')}")
                    else:
                        print(f"✗ Parse failed")
                except Exception as e:
                    print(f"✗ Error: {e}")
                    import traceback
                    traceback.print_exc()

        print(f"✓ Extracted {chart_count} charts from document\n")
        return charts
    except Exception as e:
        print(f"Error in extract_charts_from_docx: {e}")
        import traceback
        traceback.print_exc()
        return []


def parse_chart_xml(chart_bytes: bytes, rel_id: str = None) -> Optional[Dict[str, Any]]:
    """Parse Office Open XML chart format and extract data."""
    try:
        # Parse XML
        root = etree.fromstring(chart_bytes)

        # Define namespaces
        namespaces = {
            'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        }

        # Get chart type
        chart_type = get_chart_type(root, namespaces)

        # Get chart title
        title = get_chart_title(root, namespaces)

        # Get series data
        series_list = extract_series_data(root, namespaces)

        # Get categories
        categories = extract_categories(root, namespaces)

        # Get colors/styling
        colors = extract_colors(root, namespaces)

        if not series_list or not categories:
            rel_info = f" ({rel_id})" if rel_id else ""
            print(f"  ✗ Chart parsing failed{rel_info}: title='{title}', type={chart_type}")
            print(f"    → {len(series_list)} series, {len(categories)} categories")
            if series_list:
                for i, s in enumerate(series_list):
                    print(f"      Series {i}: {s['name']} with {len(s['data'])} values")
            if categories:
                print(f"      Categories: {categories[:3]}{'...' if len(categories) > 3 else ''}")
            return None

        return {
            'type': chart_type,
            'title': title,
            'categories': categories,
            'series': series_list,
            'colors': colors,
            'raw_xml': chart_bytes
        }
    except Exception as e:
        rel_info = f" ({rel_id})" if rel_id else ""
        print(f"  ✗ Exception parsing chart XML{rel_info}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_chart_type(root, namespaces: Dict) -> str:
    """Determine chart type from XML."""
    # Check for different chart types
    if root.find('.//c:barChart', namespaces) is not None:
        bar_chart = root.find('.//c:barChart', namespaces)
        # Check if it's horizontal (grouping = barDir)
        bar_dir = bar_chart.find('.//c:barDir', namespaces)
        if bar_dir is not None and bar_dir.get('val') == 'bar':
            return 'horizontalBar'
        return 'bar'  # Vertical bar
    elif root.find('.//c:lineChart', namespaces) is not None:
        return 'line'
    elif root.find('.//c:pieChart', namespaces) is not None:
        return 'pie'
    elif root.find('.//c:doughnutChart', namespaces) is not None:
        return 'doughnut'
    elif root.find('.//c:areaChart', namespaces) is not None:
        return 'area'
    elif root.find('.//c:scatterChart', namespaces) is not None:
        return 'scatter'

    return 'bar'  # Default


def get_chart_title(root, namespaces: Dict) -> str:
    """Extract chart title."""
    title_elem = root.find('.//c:title', namespaces)
    if title_elem is not None:
        # Look for text in rich text
        text_elem = title_elem.find('.//a:t', namespaces)
        if text_elem is not None:
            return text_elem.text or ''
    return ''


def extract_categories(root, namespaces: Dict) -> List[str]:
    """Extract category labels (X-axis)."""
    categories = []

    # For bar charts, categories come from the cat element
    cat_data = root.find('.//c:cat', namespaces)
    if cat_data is None:
        # Alternative path
        cat_data = root.find('.//c:strRef/c:strCache', namespaces)

    if cat_data is not None:
        # Extract text values
        pt_elements = cat_data.findall('.//c:pt', namespaces)
        for pt in pt_elements:
            text_elem = pt.find('.//a:t', namespaces)
            if text_elem is not None and text_elem.text:
                categories.append(text_elem.text)

        if not categories:
            # Try alternative structure
            v_elements = cat_data.findall('.//c:v', namespaces)
            for v in v_elements:
                if v.text:
                    categories.append(v.text)

    return categories


def extract_series_data(root, namespaces: Dict) -> List[Dict[str, Any]]:
    """Extract all data series with proper names."""
    series_list = []

    # Find all series
    series_elements = root.findall('.//c:ser', namespaces)

    for ser_idx, ser in enumerate(series_elements):
        # Get series name from different possible locations
        ser_name = None

        # Try path 1: tx/strRef/strCache/pt/a:t
        ser_title_elem = ser.find('.//c:tx/c:strRef/c:strCache/c:pt/a:t', namespaces)
        if ser_title_elem is not None and ser_title_elem.text:
            ser_name = ser_title_elem.text

        # Try path 2: tx/v (direct value)
        if not ser_name:
            tx_elem = ser.find('.//c:tx/c:v', namespaces)
            if tx_elem is not None and tx_elem.text:
                ser_name = tx_elem.text

        # Try path 3: tx/strRef/strCache/v (fallback for text values)
        if not ser_name:
            cache_v = ser.find('.//c:tx/c:strRef/c:strCache/c:v', namespaces)
            if cache_v is not None and cache_v.text:
                ser_name = cache_v.text

        # Try path 4: Check if formula refers to a label
        # For now, use fallback names that match the chart legend
        if not ser_name or ser_name.startswith('$'):
            if ser_idx == 0:
                ser_name = 'التصنيف الأصلي'
            elif ser_idx == 1:
                ser_name = 'التصنيف الصحيح'
            else:
                ser_name = f'Series {ser_idx + 1}'

        # Try path 4: dLbls (data label)
        if not ser_name:
            dlbl = ser.find('.//c:dLbls', namespaces)
            if dlbl is not None:
                # Get name from first data label
                text_elem = dlbl.find('.//a:t', namespaces)
                if text_elem is not None and text_elem.text:
                    ser_name = text_elem.text

        # Fallback
        if not ser_name:
            ser_name = f'Series {ser_idx + 1}'

        # Get series data values
        val_elem = ser.find('.//c:val', namespaces)
        if val_elem is None:
            val_elem = ser.find('.//c:yVal', namespaces)

        data = []
        if val_elem is not None:
            # Find numeric cache
            num_cache = val_elem.find('.//c:numCache', namespaces)
            if num_cache is not None:
                pt_elements = num_cache.findall('.//c:pt', namespaces)

                # Check if pt elements have idx attributes (order might not be sequential)
                pt_dict = {}
                max_idx = -1
                has_idx = False

                for pt_idx, pt in enumerate(pt_elements):
                    idx_attr = pt.get('idx')
                    v_elem = pt.find('.//c:v', namespaces)
                    value = None

                    if v_elem is not None and v_elem.text:
                        try:
                            value = float(v_elem.text)
                        except ValueError:
                            value = 0

                    if idx_attr is not None:
                        has_idx = True
                        try:
                            idx = int(idx_attr)
                            max_idx = max(max_idx, idx)
                            if value is not None:
                                pt_dict[idx] = value
                        except ValueError:
                            pass
                    else:
                        # No idx, just add in order
                        if value is not None:
                            data.append(value)

                # If we found idx attributes, build data array in order
                if has_idx and pt_dict:
                    data = []
                    for i in range(max_idx + 1):
                        data.append(pt_dict.get(i, 0))

        if data:
            series_list.append({
                'name': ser_name,
                'data': data
            })

    return series_list


def extract_colors(root, namespaces: Dict) -> List[str]:
    """Extract color scheme from chart.

    For pie/doughnut charts: extracts colors from individual data points (c:dPt).
    For other charts: extracts colors from series level.
    """
    colors = []

    # Check if this is a pie/doughnut chart
    pie_type = root.find('.//c:pieChart', namespaces) is not None
    doughnut_type = root.find('.//c:doughnutChart', namespaces) is not None
    is_pie = pie_type or doughnut_type

    if is_pie:
        # For pie charts: extract color from each data point (c:dPt)
        series_elements = root.findall('.//c:ser', namespaces)
        if series_elements:
            ser = series_elements[0]  # Pie charts have one series

            # First, get all data points to know how many we need colors for
            val_elem = ser.find('.//c:val', namespaces)
            num_data_points = 0
            if val_elem is not None:
                num_cache = val_elem.find('.//c:numCache', namespaces)
                if num_cache is not None:
                    pt_elements = num_cache.findall('.//c:pt', namespaces)
                    num_data_points = len(pt_elements)

            # Create a dict of index -> color from dPt elements
            dpt_colors = {}
            data_points = ser.findall('.//c:dPt', namespaces)

            for dpt_idx, dpt in enumerate(data_points):
                idx_attr = dpt.get('idx')
                if idx_attr is not None:
                    try:
                        idx = int(idx_attr)
                        solid_fill = dpt.find('.//a:solidFill', namespaces)
                        if solid_fill is not None:
                            srgb = solid_fill.find('.//a:srgbClr', namespaces)
                            if srgb is not None:
                                color_val = srgb.get('val')
                                if color_val:
                                    dpt_colors[idx] = f'#{color_val}'
                    except ValueError:
                        pass

            # Build colors array in order of data points, using dPt colors when available
            # Since dPt elements usually don't have idx attributes, use a smarter default
            # For pie charts, use colors that work well: green, gray, tan
            pie_default_colors = ['#2D6B3C', '#808080', '#B68A35']  # green, gray, tan
            default_colors = ['#2E5090', '#87CEEB', '#4682B4', '#ADD8E6', '#FFB347', '#98D8C8']

            if num_data_points > 0:
                # We have data points, build colors for each
                for i in range(num_data_points):
                    if i in dpt_colors:
                        color = dpt_colors[i]
                        colors.append(color)
                    else:
                        # Use pie-specific colors if available, otherwise generic defaults
                        if len(pie_default_colors) > 0:
                            color = pie_default_colors[i % len(pie_default_colors)]
                        else:
                            color = default_colors[i % len(default_colors)]
                        colors.append(color)
            else:
                # No individual data points, fall back to series color
                series_elements = root.findall('.//c:ser', namespaces)
                for ser in series_elements:
                    solid_fill = ser.find('.//a:solidFill', namespaces)
                    if solid_fill is not None:
                        srgb = solid_fill.find('.//a:srgbClr', namespaces)
                        if srgb is not None:
                            color_val = srgb.get('val')
                            if color_val:
                                colors.append(f'#{color_val}')
                                continue
                    # Default fallback
                    default_colors = ['#2E5090', '#87CEEB', '#4682B4', '#ADD8E6']
                    colors.append(default_colors[len(colors) % len(default_colors)])
    else:
        # For non-pie charts: extract colors from series
        series_elements = root.findall('.//c:ser', namespaces)

        for ser in series_elements:
            # Look for solidFill color
            solid_fill = ser.find('.//a:solidFill', namespaces)
            if solid_fill is not None:
                # Try srgbClr (RGB color)
                srgb = solid_fill.find('.//a:srgbClr', namespaces)
                if srgb is not None:
                    color_val = srgb.get('val')
                    if color_val:
                        colors.append(f'#{color_val}')
                        continue

                # Try schemeClr (theme color) - these are harder to extract
                scheme = solid_fill.find('.//a:schemeClr', namespaces)
                if scheme is not None:
                    # Use default colors based on position
                    pass

            # If no color found, use default colors
            if len(colors) < len(series_elements):
                # Use default blue/light blue colors
                default_colors = ['#2E5090', '#87CEEB', '#4682B4', '#ADD8E6']
                colors.append(default_colors[len(colors) % len(default_colors)])

    return colors if colors else ['#2E5090', '#87CEEB']


def get_chart_by_title(docx_path: str, title_contains: str) -> Optional[Dict[str, Any]]:
    """Find a specific chart by title substring."""
    charts = extract_charts_from_docx(docx_path)
    for chart in charts:
        if title_contains.lower() in chart['title'].lower():
            return chart
    return None
