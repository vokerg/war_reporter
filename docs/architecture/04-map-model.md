# Map model

## Stack

The intended publication stack is MapLibre GL JS, GeoJSON for current/small layers, and PMTiles for large historical layers. Basemap licensing, attribution, and tile-provider policy must be documented before deployment.

## Coordinate and time model

GeoJSON uses WGS 84 longitude/latitude order. Every feature records validity time, assessment time, release threshold, precision, uncertainty method, publication status, claims, and observations.

## Feature classes

`frontline_assessment`, `territorial_control_assessment`, `reported_presence`, `confirmed_presence`, `strike_report`, `strike_assessment`, `explosion_report`, `damaged_infrastructure`, `destroyed_infrastructure`, `evacuation`, `fortification`, `bridge_status`, `crossing`, `logistics_route`, and `uncertainty_area`.

## Uncertainty and supersession

Do not publish a single falsely precise frontline. Use uncertainty polygons/bands, generalized geometry, visible “as of” timestamps, separate reported-presence and assessed-control layers, and immutable snapshots. A newer feature supersedes rather than silently edits a released feature.

## Public/private boundary

`withheld` features have null geometry. `delayed` features are not released before `publish_not_before`. `coarsened` features contain only reviewed generalized geometry. A public build must exclude restricted artifacts and non-public internal geometry.
