# Map model

## Recommended publication stack

Use MapLibre GL JS for the client map, GeoJSON for current and small layers, and PMTiles for large historical layers. Basemap usage must comply with the selected provider's policy.

## Feature classes

- `frontline_assessment`
- `territorial_control_assessment`
- `reported_presence`
- `confirmed_presence`
- `strike_report`
- `strike_assessment`
- `explosion_report`
- `damaged_infrastructure`
- `destroyed_infrastructure`
- `evacuation`
- `fortification`
- `bridge_status`
- `crossing`
- `logistics_route`
- `uncertainty_area`

## Uncertainty

Do not publish one falsely precise frontline. Represent confidence using geometry precision, uncertainty areas, assessment timestamps, timeline snapshots, and separate layers for reported presence and assessed control.

Every feature must link to claims and evidence and declare whether it supersedes an earlier feature.
