/**
 * Smart Route Optimizer - Frontend Controller
 * ============================================
 * Handles dual-mode map initialization (Google Maps with Leaflet fallback),
 * place search, custom numbered markers, stop management, benchmark presets,
 * dynamic API communication (POST /api/optimize, POST /api/route),
 * polyline route rendering, side-by-side comparison tables, and
 * pure HTML5 Canvas analytics charts (cost bar chart & convergence curve).
 */

(function () {
    "use strict";

    // Application State
    const state = {
        stops: [], // Array of { id, label, lat, lng }
        mapProvider: "none", // 'google' or 'leaflet'
        map: null,
        markers: [], // Array of marker instances
        optimizedPolylineLayer: null,
        baselinePolylineLayer: null,
        lastOptimizationResult: null,
        currentChartType: "bar", // 'bar' or 'convergence'
        maxStops: 15,
        defaultCenter: { lat: 12.9716, lng: 77.5946 }, // Bangalore default
    };

    // Benchmark Route Presets
    const PRESETS = {
        bangalore: [
            { label: "Start: Majestic Bus Station", lat: 12.9784, lng: 77.5726 },
            { label: "Stop 1: Indiranagar 100ft Rd", lat: 12.9719, lng: 77.6412 },
            { label: "Stop 2: Koramangala 5th Block", lat: 12.9352, lng: 77.6245 },
            { label: "Stop 3: Whitefield ITPL", lat: 12.9698, lng: 77.7499 },
            { label: "Destination: Kempegowda Airport", lat: 13.1986, lng: 77.7066 },
        ],
        linear_benchmark: [
            { label: "Start: Point A (0 km)", lat: 12.9716, lng: 77.5946 },
            { label: "Stop 1: Point C (30 km east)", lat: 12.9716, lng: 77.8646 },
            { label: "Stop 2: Point B (10 km east)", lat: 12.9716, lng: 77.6846 },
            { label: "Stop 3: Point D (40 km east)", lat: 12.9716, lng: 77.9546 },
            { label: "Destination: Point E (50 km east)", lat: 12.9716, lng: 78.0446 },
        ],
        nyc: [
            { label: "Start: Battery Park", lat: 40.7033, lng: -74.0170 },
            { label: "Stop 1: Empire State Building", lat: 40.7484, lng: -73.9857 },
            { label: "Stop 2: High Line Park", lat: 40.7480, lng: -74.0048 },
            { label: "Stop 3: Times Square", lat: 40.7580, lng: -73.9855 },
            { label: "Stop 4: Central Park Zoo", lat: 40.7678, lng: -73.9718 },
            { label: "Destination: Columbia University", lat: 40.8075, lng: -73.9626 },
        ],
        london: [
            { label: "Start: Tower Bridge", lat: 51.5055, lng: -0.0754 },
            { label: "Stop 1: Big Ben & Parliament", lat: 51.5007, lng: -0.1246 },
            { label: "Stop 2: British Museum", lat: 51.5194, lng: -0.1270 },
            { label: "Stop 3: Hyde Park Corner", lat: 51.5033, lng: -0.1517 },
            { label: "Destination: Camden Market", lat: 51.5414, lng: -0.1466 },
        ],
    };

    // DOM Elements
    const elements = {
        stopsContainer: document.getElementById("stops-container"),
        stopsCounter: document.getElementById("stops-counter"),
        searchInput: document.getElementById("place-search-input"),
        btnAddSearched: document.getElementById("btn-add-searched-stop"),
        btnAddStop: document.getElementById("btn-add-stop"),
        btnResetStops: document.getElementById("btn-reset-stops"),
        presetSelect: document.getElementById("preset-select"),
        btnOptimize: document.getElementById("btn-optimize"),
        statusSpinner: document.getElementById("status-spinner"),
        spinnerText: document.getElementById("spinner-text"),
        errorMessage: document.getElementById("error-message"),
        resultsPanel: document.getElementById("results-panel"),
        btnCloseResults: document.getElementById("btn-close-results"),
        mapLegend: document.getElementById("map-legend"),
        chkShowOptimized: document.getElementById("chk-show-optimized"),
        chkShowBaseline: document.getElementById("chk-show-baseline"),
        resultsDatasourceBadge: document.getElementById("results-datasource-badge"),
        metricOptDist: document.getElementById("metric-opt-dist"),
        metricBaseDist: document.getElementById("metric-base-dist"),
        metricOptTime: document.getElementById("metric-opt-time"),
        metricBaseTime: document.getElementById("metric-base-time"),
        metricImprovement: document.getElementById("metric-improvement"),
        metricSavingsDetail: document.getElementById("metric-savings-detail"),
        tblBaseDist: document.getElementById("tbl-base-dist"),
        tblOptDist: document.getElementById("tbl-opt-dist"),
        tblDiffDist: document.getElementById("tbl-diff-dist"),
        tblBaseTime: document.getElementById("tbl-base-time"),
        tblOptTime: document.getElementById("tbl-opt-time"),
        tblDiffTime: document.getElementById("tbl-diff-time"),
        tblBaseSeq: document.getElementById("tbl-base-seq"),
        tblOptSeq: document.getElementById("tbl-opt-seq"),
        tblOrderStatus: document.getElementById("tbl-order-status"),
        chartTitle: document.getElementById("chart-title"),
        tabBarChart: document.getElementById("tab-bar-chart"),
        tabConvergenceChart: document.getElementById("tab-convergence-chart"),
        analyticsCanvas: document.getElementById("analytics-canvas"),
        itineraryList: document.getElementById("itinerary-list"),
        btnInfo: document.getElementById("btn-info"),
        infoModal: document.getElementById("info-modal"),
        btnCloseModal: document.getElementById("btn-close-modal"),
        btnResetParams: document.getElementById("btn-reset-params"),
        dataSourceBadge: document.getElementById("data-source-badge"),
        badgeText: document.getElementById("badge-text"),
    };

    /* ==========================================================================
       INITIALIZATION
       ========================================================================== */

    function init() {
        setupEventListeners();

        // Check if Google Maps JS API loaded successfully
        if (window.google && window.google.maps) {
            initGoogleMaps();
        } else {
            // Fallback to Leaflet with OpenStreetMap
            initLeafletMap();
        }

        // Load default benchmark preset
        loadPreset("bangalore");
    }

    /* ==========================================================================
       MAP PROVIDER INITIALIZERS
       ========================================================================== */

    window.initGoogleMaps = function () {
        if (state.mapProvider === "google") return;
        state.mapProvider = "google";

        const mapOptions = {
            center: state.defaultCenter,
            zoom: 12,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: true,
            styles: [
                { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] }
            ]
        };

        state.map = new google.maps.Map(document.getElementById("map"), mapOptions);

        state.map.addListener("click", (e) => {
            const lat = e.latLng.lat();
            const lng = e.latLng.lng();
            addNewStop(lat, lng);
        });

        if (elements.searchInput && google.maps.places) {
            const autocomplete = new google.maps.places.Autocomplete(elements.searchInput, {
                fields: ["geometry", "name", "formatted_address"],
            });
            autocomplete.bindTo("bounds", state.map);

            autocomplete.addListener("place_changed", () => {
                const place = autocomplete.getPlace();
                if (!place.geometry || !place.geometry.location) {
                    showError("No location details available for selected place.");
                    return;
                }
                const lat = place.geometry.location.lat();
                const lng = place.geometry.location.lng();
                const label = place.name || place.formatted_address || "Searched Stop";
                addNewStop(lat, lng, label);
                elements.searchInput.value = "";
            });
        }

        refreshMapMarkers();
    };

    function initLeafletMap() {
        if (state.mapProvider === "leaflet") return;
        state.mapProvider = "leaflet";

        state.map = L.map("map").setView([state.defaultCenter.lat, state.defaultCenter.lng], 12);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(state.map);

        state.map.on("click", (e) => {
            addNewStop(e.latlng.lat, e.latlng.lng);
        });

        elements.btnAddSearched.addEventListener("click", () => {
            geocodeAndAddStop(elements.searchInput.value);
        });
        elements.searchInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                geocodeAndAddStop(elements.searchInput.value);
            }
        });

        refreshMapMarkers();
    }

    function geocodeAndAddStop(query) {
        if (!query || !query.trim()) return;
        const q = query.trim();
        showSpinner("Searching location...");

        fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&limit=1`)
            .then((res) => res.json())
            .then((data) => {
                hideSpinner();
                if (data && data.length > 0) {
                    const lat = parseFloat(data[0].lat);
                    const lng = parseFloat(data[0].lon);
                    const label = data[0].display_name.split(",")[0] || q;
                    addNewStop(lat, lng, label);
                    elements.searchInput.value = "";
                } else {
                    showError(`Location '${q}' not found. Try clicking directly on the map.`);
                }
            })
            .catch(() => {
                hideSpinner();
                showError("Geocoding service unavailable. Please click directly on the map.");
            });
    }

    /* ==========================================================================
       POLYLINE DECODER (STANDALONE UTILITY)
       ========================================================================== */

    function decodePolyline(encoded) {
        if (!encoded) return [];
        let index = 0, lat = 0, lng = 0, coordinates = [];
        while (index < encoded.length) {
            let b, shift = 0, result = 0;
            do {
                b = encoded.charCodeAt(index++) - 63;
                result |= (b & 0x1f) << shift;
                shift += 5;
            } while (b >= 0x20);
            let dlat = (result & 1) ? ~(result >> 1) : (result >> 1);
            lat += dlat;

            shift = 0; result = 0;
            do {
                b = encoded.charCodeAt(index++) - 63;
                result |= (b & 0x1f) << shift;
                shift += 5;
            } while (b >= 0x20);
            let dlng = (result & 1) ? ~(result >> 1) : (result >> 1);
            lng += dlng;

            coordinates.push([lat / 1e5, lng / 1e5]);
        }
        return coordinates;
    }

    /* ==========================================================================
       STOP MANAGEMENT
       ========================================================================== */

    function addNewStop(lat, lng, customLabel = null) {
        if (state.stops.length >= state.maxStops) {
            showError(`Maximum ${state.maxStops} stops reached. Remove a stop before adding more.`);
            return;
        }

        const id = "stop_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5);
        let defaultLabel = `Stop ${state.stops.length}`;
        if (state.stops.length === 0) defaultLabel = "Start Point";
        else if (state.stops.length === 1) defaultLabel = "Destination";

        const label = customLabel || defaultLabel;

        state.stops.push({
            id: id,
            label: label,
            lat: parseFloat(lat.toFixed(5)),
            lng: parseFloat(lng.toFixed(5)),
        });

        clearRoutePolylines();
        hideError();
        renderStopsList();
        refreshMapMarkers();
        fitMapToBounds();
    }

    function removeStop(index) {
        if (index < 0 || index >= state.stops.length) return;
        state.stops.splice(index, 1);
        clearRoutePolylines();
        renderStopsList();
        refreshMapMarkers();
        fitMapToBounds();
    }

    function moveStop(index, direction) {
        const targetIndex = index + direction;
        if (targetIndex < 0 || targetIndex >= state.stops.length) return;

        const temp = state.stops[index];
        state.stops[index] = state.stops[targetIndex];
        state.stops[targetIndex] = temp;

        clearRoutePolylines();
        renderStopsList();
        refreshMapMarkers();
    }

    function updateStopLabel(index, newLabel) {
        if (index >= 0 && index < state.stops.length) {
            state.stops[index].label = newLabel.trim() || `Stop ${index}`;
        }
    }

    function resetAllStops() {
        state.stops = [];
        clearMapLayers();
        clearRoutePolylines();
        renderStopsList();
        hideError();
        if (elements.resultsPanel) {
            elements.resultsPanel.classList.add("hidden");
        }
        if (elements.mapLegend) {
            elements.mapLegend.classList.add("hidden");
        }
    }

    function loadPreset(presetKey) {
        const preset = PRESETS[presetKey];
        if (!preset) return;

        state.stops = [];
        preset.forEach((stop, idx) => {
            state.stops.push({
                id: "preset_" + idx,
                label: stop.label,
                lat: stop.lat,
                lng: stop.lng,
            });
        });

        clearRoutePolylines();
        if (elements.resultsPanel) {
            elements.resultsPanel.classList.add("hidden");
        }
        if (elements.mapLegend) {
            elements.mapLegend.classList.add("hidden");
        }

        renderStopsList();
        refreshMapMarkers();
        fitMapToBounds();
        hideError();
    }

    /* ==========================================================================
       SIDEBAR RENDERING
       ========================================================================== */

    function renderStopsList() {
        elements.stopsContainer.innerHTML = "";
        const total = state.stops.length;
        elements.stopsCounter.textContent = `${total} / ${state.maxStops} stops`;

        if (total === 0) {
            elements.stopsContainer.innerHTML = `
                <div class="empty-stops-prompt" style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                    🗺️ No stops added yet.<br>Click anywhere on the map or choose a preset route above.
                </div>
            `;
            return;
        }

        state.stops.forEach((stop, idx) => {
            const isStart = idx === 0;
            const isDest = idx === total - 1 && total > 1;

            let badgeClass = "badge-intermediate";
            let badgeText = `${idx}`;
            if (isStart) {
                badgeClass = "badge-start";
                badgeText = "S";
            } else if (isDest) {
                badgeClass = "badge-dest";
                badgeText = "D";
            }

            const item = document.createElement("div");
            item.className = "stop-item";
            item.dataset.index = idx;

            item.innerHTML = `
                <div class="stop-badge ${badgeClass}">${badgeText}</div>
                <div class="stop-info">
                    <input type="text" class="stop-label-input" value="${escapeHtml(stop.label)}" data-index="${idx}">
                    <div class="stop-coords">${stop.lat.toFixed(4)}, ${stop.lng.toFixed(4)}</div>
                </div>
                <div class="stop-controls">
                    <button type="button" class="btn-ctrl btn-up" data-index="${idx}" ${idx === 0 ? "disabled" : ""} title="Move up">▲</button>
                    <button type="button" class="btn-ctrl btn-down" data-index="${idx}" ${idx === total - 1 ? "disabled" : ""} title="Move down">▼</button>
                    <button type="button" class="btn-ctrl btn-remove" data-index="${idx}" title="Remove stop">✕</button>
                </div>
            `;

            const labelInput = item.querySelector(".stop-label-input");
            labelInput.addEventListener("change", (e) => {
                updateStopLabel(idx, e.target.value);
            });

            const btnUp = item.querySelector(".btn-up");
            btnUp.addEventListener("click", () => moveStop(idx, -1));

            const btnDown = item.querySelector(".btn-down");
            btnDown.addEventListener("click", () => moveStop(idx, 1));

            const btnRemove = item.querySelector(".btn-remove");
            btnRemove.addEventListener("click", () => removeStop(idx));

            elements.stopsContainer.appendChild(item);
        });
    }

    /* ==========================================================================
       MAP MARKERS & POLYLINES
       ========================================================================== */

    function clearMapLayers() {
        if (state.mapProvider === "google") {
            state.markers.forEach((m) => m.setMap(null));
            state.markers = [];
        } else if (state.mapProvider === "leaflet") {
            state.markers.forEach((m) => state.map.removeLayer(m));
            state.markers = [];
        }
    }

    function clearRoutePolylines() {
        if (state.mapProvider === "google") {
            if (state.optimizedPolylineLayer) {
                state.optimizedPolylineLayer.setMap(null);
                state.optimizedPolylineLayer = null;
            }
            if (state.baselinePolylineLayer) {
                state.baselinePolylineLayer.setMap(null);
                state.baselinePolylineLayer = null;
            }
        } else if (state.mapProvider === "leaflet") {
            if (state.optimizedPolylineLayer) {
                state.map.removeLayer(state.optimizedPolylineLayer);
                state.optimizedPolylineLayer = null;
            }
            if (state.baselinePolylineLayer) {
                state.map.removeLayer(state.baselinePolylineLayer);
                state.baselinePolylineLayer = null;
            }
        }
    }

    function refreshMapMarkers(tourOrder = null) {
        if (!state.map) return;
        clearMapLayers();

        const total = state.stops.length;
        if (total === 0) return;

        state.stops.forEach((stop, originalIdx) => {
            let visitIndex = originalIdx;
            if (tourOrder && Array.isArray(tourOrder)) {
                visitIndex = tourOrder.indexOf(originalIdx);
            }

            const isStart = visitIndex === 0;
            const isDest = visitIndex === total - 1 && total > 1;

            let labelText = `${visitIndex}`;
            let markerColor = "#3b82f6";
            if (isStart) {
                labelText = "S";
                markerColor = "#10b981";
            } else if (isDest) {
                labelText = "D";
                markerColor = "#ef4444";
            }

            if (state.mapProvider === "google") {
                const marker = new google.maps.Marker({
                    position: { lat: stop.lat, lng: stop.lng },
                    map: state.map,
                    title: `${stop.label} (Visit #${visitIndex})`,
                    label: {
                        text: labelText,
                        color: "#ffffff",
                        fontWeight: "700",
                        fontSize: "12px",
                    },
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        fillColor: markerColor,
                        fillOpacity: 1.0,
                        strokeColor: "#ffffff",
                        strokeWeight: 2,
                        scale: 14,
                    },
                });

                const infoWindow = new google.maps.InfoWindow({
                    content: `<strong>${escapeHtml(stop.label)}</strong><br>Visiting Order: <strong>#${visitIndex}</strong><br><small>${stop.lat}, ${stop.lng}</small>`,
                });
                marker.addListener("click", () => {
                    infoWindow.open(state.map, marker);
                });

                state.markers.push(marker);
            } else if (state.mapProvider === "leaflet") {
                let badgeClass = "marker-intermediate";
                if (isStart) badgeClass = "marker-start";
                else if (isDest) badgeClass = "marker-dest";

                const icon = L.divIcon({
                    className: "leaflet-custom-div-icon",
                    html: `<div class="custom-map-marker ${badgeClass}" style="width: 28px; height: 28px;">${labelText}</div>`,
                    iconSize: [28, 28],
                    iconAnchor: [14, 14],
                });

                const marker = L.marker([stop.lat, stop.lng], { icon: icon }).addTo(state.map);
                marker.bindPopup(`<strong>${escapeHtml(stop.label)}</strong><br>Visiting Order: <strong>#${visitIndex}</strong><br><small>${stop.lat}, ${stop.lng}</small>`);
                state.markers.push(marker);
            }
        });
    }

    function renderRoutePolylines(optPolyline, basePolyline) {
        clearRoutePolylines();

        const optCoords = decodePolyline(optPolyline);
        const baseCoords = decodePolyline(basePolyline);

        if (state.mapProvider === "google") {
            // Baseline Path (dashed gray)
            if (baseCoords.length > 0) {
                const baseGooglePath = baseCoords.map(([lat, lng]) => ({ lat, lng }));
                state.baselinePolylineLayer = new google.maps.Polyline({
                    path: baseGooglePath,
                    strokeColor: "#94a3b8",
                    strokeOpacity: 0.65,
                    strokeWeight: 3,
                    map: state.map,
                });
            }

            // Optimized ACO Path (bold blue)
            if (optCoords.length > 0) {
                const optGooglePath = optCoords.map(([lat, lng]) => ({ lat, lng }));
                state.optimizedPolylineLayer = new google.maps.Polyline({
                    path: optGooglePath,
                    strokeColor: "#2563eb",
                    strokeOpacity: 0.9,
                    strokeWeight: 5,
                    map: state.map,
                });

                const bounds = new google.maps.LatLngBounds();
                optGooglePath.forEach((pt) => bounds.extend(pt));
                state.map.fitBounds(bounds);
            }
        } else if (state.mapProvider === "leaflet") {
            // Baseline Path
            if (baseCoords.length > 0) {
                state.baselinePolylineLayer = L.polyline(baseCoords, {
                    color: "#94a3b8",
                    weight: 3,
                    opacity: 0.65,
                    dashArray: "6, 6",
                }).addTo(state.map);
            }

            // Optimized ACO Path
            if (optCoords.length > 0) {
                state.optimizedPolylineLayer = L.polyline(optCoords, {
                    color: "#2563eb",
                    weight: 5,
                    opacity: 0.9,
                }).addTo(state.map);

                state.map.fitBounds(state.optimizedPolylineLayer.getBounds(), { padding: [40, 40] });
            }
        }

        if (elements.mapLegend) {
            elements.mapLegend.classList.remove("hidden");
        }
    }

    function fitMapToBounds() {
        if (!state.map || state.stops.length === 0) return;

        if (state.mapProvider === "google") {
            const bounds = new google.maps.LatLngBounds();
            state.stops.forEach((s) => bounds.extend({ lat: s.lat, lng: s.lng }));
            state.map.fitBounds(bounds);
            if (state.stops.length === 1) state.map.setZoom(13);
        } else if (state.mapProvider === "leaflet") {
            const latLngs = state.stops.map((s) => [s.lat, s.lng]);
            state.map.fitBounds(latLngs, { padding: [40, 40], maxZoom: 14 });
        }
    }

    /* ==========================================================================
       OPTIMIZATION PIPELINE & CHARTS
       ========================================================================== */

    function runOptimization() {
        if (state.stops.length < 2) {
            showError("At least 2 stops (start and destination) are required to optimize.");
            return;
        }

        hideError();

        const numAnts = parseInt(document.getElementById("param-ants").value, 10) || 20;
        const iterations = parseInt(document.getElementById("param-iterations").value, 10) || 40;
        const alpha = parseFloat(document.getElementById("param-alpha").value) || 1.0;
        const beta = parseFloat(document.getElementById("param-beta").value) || 2.5;
        const evaporationRate = parseFloat(document.getElementById("param-evaporation").value) || 0.2;
        const q = parseFloat(document.getElementById("param-q").value) || 100.0;
        const seedVal = document.getElementById("param-seed").value.trim();
        const randomSeed = seedVal !== "" ? parseInt(seedVal, 10) : null;

        const objectiveRadio = document.querySelector('input[name="opt-objective"]:checked');
        const objective = objectiveRadio ? objectiveRadio.value : "distance";

        const payload = {
            stops: state.stops.map((s, idx) => ({
                lat: s.lat,
                lng: s.lng,
                label: s.label || `Stop ${idx}`,
            })),
            objective: objective,
            aco_params: {
                num_ants: numAnts,
                iterations: iterations,
                alpha: alpha,
                beta: beta,
                evaporation_rate: evaporationRate,
                q: q,
                random_seed: randomSeed,
            },
        };

        showSpinner(`Dispatching ${numAnts} ants over ${iterations} iterations...`);

        fetch("/api/optimize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then(async (response) => {
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.message || `Server returned HTTP ${response.status}`);
                }
                return data;
            })
            .then((data) => {
                hideSpinner();
                handleOptimizationSuccess(data);
            })
            .catch((err) => {
                hideSpinner();
                showError(`Optimization Error: ${err.message}`);
            });
    }

    function handleOptimizationSuccess(data) {
        state.lastOptimizationResult = data;

        // Update data source badges
        if (elements.badgeText && elements.dataSourceBadge) {
            elements.badgeText.textContent = data.dataSource;
            elements.dataSourceBadge.className = data.isSimulated ? "badge badge-demo" : "badge badge-live";
        }
        if (elements.resultsDatasourceBadge) {
            elements.resultsDatasourceBadge.textContent = data.dataSource;
            elements.resultsDatasourceBadge.className = data.isSimulated ? "badge badge-demo" : "badge badge-live";
        }

        // 1. Render Polylines
        const optPolyline = data.route_geometry ? data.route_geometry.polyline : "";
        const basePolyline = data.route_geometry ? data.route_geometry.baseline_polyline : "";
        renderRoutePolylines(optPolyline, basePolyline);

        // 2. Re-number Map Markers according to ACO tour visiting order
        refreshMapMarkers(data.optimized.tour);

        // 3. Render Results Panel (Metrics, Table, Chart, Itinerary)
        renderResultsPanel(data);
    }

    function renderResultsPanel(data) {
        const opt = data.optimized;
        const base = data.baseline;
        const metrics = data.metrics;

        // Metric summary cards
        elements.metricOptDist.textContent = `${opt.total_distance_km} km`;
        elements.metricBaseDist.textContent = `Original: ${base.total_distance_km} km`;

        elements.metricOptTime.textContent = `${opt.total_duration_minutes} min`;
        elements.metricBaseTime.textContent = `Original: ${base.total_duration_minutes} min`;

        const improvementSign = metrics.percentage_improvement >= 0 ? "+" : "";
        elements.metricImprovement.textContent = `${improvementSign}${metrics.percentage_improvement}%`;

        let savingsText = `Saved ${metrics.distance_saved_km} km (${metrics.duration_saved_minutes} min)`;
        if (metrics.percentage_improvement <= 0) {
            savingsText = "Original order was already near-optimal";
        }
        elements.metricSavingsDetail.textContent = savingsText;

        // Populate Comparative Table
        elements.tblBaseDist.textContent = `${base.total_distance_km} km (${base.total_distance_meters.toLocaleString()} m)`;
        elements.tblOptDist.textContent = `${opt.total_distance_km} km (${opt.total_distance_meters.toLocaleString()} m)`;
        elements.tblDiffDist.textContent = `-${metrics.distance_saved_km} km (${metrics.percentage_improvement}%)`;

        elements.tblBaseTime.textContent = `${base.total_duration_minutes} min (${Math.round(base.total_duration_seconds)}s)`;
        elements.tblOptTime.textContent = `${opt.total_duration_minutes} min (${Math.round(opt.total_duration_seconds)}s)`;
        elements.tblDiffTime.textContent = `-${metrics.duration_saved_minutes} min (${metrics.percentage_improvement}%)`;

        // Format compact stop sequences: S -> 1 -> 2 -> ... -> D
        elements.tblBaseSeq.textContent = formatSequence(base.tour);
        elements.tblOptSeq.textContent = formatSequence(opt.tour);

        const isOrderChanged = JSON.stringify(base.tour) !== JSON.stringify(opt.tour);
        elements.tblOrderStatus.textContent = isOrderChanged ? "Optimized Order" : "Same Order (Already Optimal)";
        elements.tblOrderStatus.className = isOrderChanged ? "badge badge-live" : "badge badge-neutral";

        // Render Active Analytics Chart
        renderAnalyticsChart();

        // Populate Itinerary Steps
        elements.itineraryList.innerHTML = "";
        const ordered = opt.ordered_stops;
        const legs = data.route_geometry ? data.route_geometry.legs : [];

        ordered.forEach((stop, idx) => {
            const isStart = idx === 0;
            const isDest = idx === ordered.length - 1;

            let badgeClass = "badge-intermediate";
            let badgeText = `${idx}`;
            if (isStart) {
                badgeClass = "badge-start";
                badgeText = "S";
            } else if (isDest) {
                badgeClass = "badge-dest";
                badgeText = "D";
            }

            const li = document.createElement("li");
            li.className = "itinerary-step";

            let legInfoHtml = "";
            if (idx < legs.length && legs[idx]) {
                const leg = legs[idx];
                legInfoHtml = `<span class="itinerary-leg-info">↳ ${leg.distance_km} km • ${leg.duration_minutes} min to next</span>`;
            }

            li.innerHTML = `
                <div class="itinerary-step-left">
                    <div class="itinerary-step-badge ${badgeClass}">${badgeText}</div>
                    <div>
                        <strong>${escapeHtml(stop.label)}</strong>
                        <div style="font-size: 0.7rem; color: var(--text-muted);">${stop.lat.toFixed(4)}, ${stop.lng.toFixed(4)}</div>
                    </div>
                </div>
                <div>${legInfoHtml}</div>
            `;
            elements.itineraryList.appendChild(li);
        });

        // Reveal results drawer
        elements.resultsPanel.classList.remove("hidden");
    }

    function formatSequence(tour) {
        if (!tour || tour.length === 0) return "--";
        const total = tour.length;
        return tour
            .map((node, i) => {
                if (i === 0) return "S";
                if (i === total - 1) return "D";
                return `${node}`;
            })
            .join(" → ");
    }

    /* ==========================================================================
       PURE HTML5 CANVAS CHARTS (NO EXTERNAL LIBS REQUIRED)
       ========================================================================== */

    function renderAnalyticsChart() {
        if (!state.lastOptimizationResult || !elements.analyticsCanvas) return;
        const canvas = elements.analyticsCanvas;
        const ctx = canvas.getContext("2d");

        // High-DPI Canvas scaling
        const dpr = window.devicePixelRatio || 1;
        const displayWidth = 500;
        const displayHeight = 240;
        canvas.width = displayWidth * dpr;
        canvas.height = displayHeight * dpr;
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, displayWidth, displayHeight);

        if (state.currentChartType === "bar") {
            drawBarComparisonChart(ctx, displayWidth, displayHeight, state.lastOptimizationResult);
        } else {
            drawConvergenceLineChart(ctx, displayWidth, displayHeight, state.lastOptimizationResult);
        }
    }

    function drawBarComparisonChart(ctx, width, height, data) {
        const isTime = data.objective === "time";
        const unit = isTime ? "min" : "km";
        const baseCost = isTime ? data.baseline.total_duration_minutes : data.baseline.total_distance_km;
        const optCost = isTime ? data.optimized.total_duration_minutes : data.optimized.total_distance_km;

        const maxVal = Math.max(baseCost, optCost) * 1.25 || 1.0;
        const chartBottom = height - 40;
        const chartTop = 30;
        const chartHeight = chartBottom - chartTop;

        const barWidth = 90;
        const baseBarX = width * 0.28 - barWidth / 2;
        const optBarX = width * 0.72 - barWidth / 2;

        const baseBarH = (baseCost / maxVal) * chartHeight;
        const optBarH = (optCost / maxVal) * chartHeight;

        // Background subtle grid lines
        ctx.strokeStyle = "#e2e8f0";
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = chartTop + (chartHeight * i) / 4;
            ctx.beginPath();
            ctx.moveTo(40, y);
            ctx.lineTo(width - 30, y);
            ctx.stroke();
        }

        // 1. Draw Baseline Bar (Slate Gray)
        ctx.fillStyle = "#94a3b8";
        ctx.beginPath();
        roundRect(ctx, baseBarX, chartBottom - baseBarH, barWidth, baseBarH, 6);
        ctx.fill();

        // 2. Draw Optimized Bar (Brand Blue)
        const gradient = ctx.createLinearGradient(0, chartBottom - optBarH, 0, chartBottom);
        gradient.addColorStop(0, "#2563eb");
        gradient.addColorStop(1, "#1d4ed8");
        ctx.fillStyle = gradient;
        ctx.beginPath();
        roundRect(ctx, optBarX, chartBottom - optBarH, barWidth, optBarH, 6);
        ctx.fill();

        // Bar Value Labels (on top of bars)
        ctx.font = "bold 13px 'JetBrains Mono', monospace";
        ctx.textAlign = "center";

        ctx.fillStyle = "#475569";
        ctx.fillText(`${baseCost.toFixed(1)} ${unit}`, baseBarX + barWidth / 2, chartBottom - baseBarH - 8);

        ctx.fillStyle = "#1e40af";
        ctx.fillText(`${optCost.toFixed(1)} ${unit}`, optBarX + barWidth / 2, chartBottom - optBarH - 8);

        // X-Axis Category Labels
        ctx.font = "600 12px Inter, sans-serif";
        ctx.fillStyle = "#64748b";
        ctx.fillText("Baseline Order", baseBarX + barWidth / 2, chartBottom + 20);
        ctx.fillStyle = "#0f172a";
        ctx.fillText("ACO Optimized", optBarX + barWidth / 2, chartBottom + 20);

        // Highlight Pill Badge
        const improvement = data.metrics.percentage_improvement;
        if (improvement > 0) {
            ctx.fillStyle = "#dcfce7";
            ctx.beginPath();
            roundRect(ctx, width / 2 - 50, 8, 100, 22, 11);
            ctx.fill();

            ctx.fillStyle = "#15803d";
            ctx.font = "bold 11px Inter, sans-serif";
            ctx.fillText(`+${improvement}% SAVED`, width / 2, 23);
        }
    }

    function drawConvergenceLineChart(ctx, width, height, data) {
        const history = data.convergence ? data.convergence.best_costs : [];
        if (!history || history.length === 0) return;

        const isTime = data.objective === "time";
        const unit = isTime ? "sec" : "m";

        const padLeft = 60;
        const padRight = 30;
        const padTop = 30;
        const padBottom = 40;

        const plotW = width - padLeft - padRight;
        const plotH = height - padTop - padBottom;

        const minCost = Math.min(...history);
        const maxCost = Math.max(...history);
        const range = maxCost - minCost || 1.0;

        // Draw axes & grid
        ctx.strokeStyle = "#e2e8f0";
        ctx.lineWidth = 1;
        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.fillStyle = "#94a3b8";
        ctx.textAlign = "right";

        for (let i = 0; i <= 4; i++) {
            const y = padTop + (plotH * i) / 4;
            const costVal = maxCost - (range * i) / 4;

            ctx.beginPath();
            ctx.moveTo(padLeft, y);
            ctx.lineTo(width - padRight, y);
            ctx.stroke();

            ctx.fillText(`${Math.round(costVal)} ${unit}`, padLeft - 8, y + 3);
        }

        // Plot Convergence Curve
        const points = history.map((val, idx) => {
            const x = padLeft + (idx / (history.length - 1)) * plotW;
            const y = padTop + plotH - ((val - minCost) / range) * plotH;
            return { x, y };
        });

        // Area Gradient under curve
        const areaGrad = ctx.createLinearGradient(0, padTop, 0, padTop + plotH);
        areaGrad.addColorStop(0, "rgba(37, 99, 235, 0.25)");
        areaGrad.addColorStop(1, "rgba(37, 99, 235, 0.0)");

        ctx.fillStyle = areaGrad;
        ctx.beginPath();
        ctx.moveTo(points[0].x, padTop + plotH);
        points.forEach((pt) => ctx.lineTo(pt.x, pt.y));
        ctx.lineTo(points[points.length - 1].x, padTop + plotH);
        ctx.closePath();
        ctx.fill();

        // Stroke line
        ctx.strokeStyle = "#2563eb";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        points.forEach((pt, idx) => {
            if (idx === 0) ctx.moveTo(pt.x, pt.y);
            else ctx.lineTo(pt.x, pt.y);
        });
        ctx.stroke();

        // Highlight first and last points
        [points[0], points[points.length - 1]].forEach((pt, i) => {
            ctx.fillStyle = i === 0 ? "#94a3b8" : "#10b981";
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 4, 0, 2 * Math.PI);
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1.5;
            ctx.stroke();
        });

        // X-Axis Labels
        ctx.font = "10px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.fillStyle = "#64748b";
        ctx.fillText("Gen 1", padLeft, height - 16);
        ctx.fillText(`Gen ${Math.round(history.length / 2)}`, padLeft + plotW / 2, height - 16);
        ctx.fillText(`Gen ${history.length} (Converged)`, width - padRight, height - 16);
    }

    function roundRect(ctx, x, y, width, height, radius) {
        if (height <= 0) return;
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height);
        ctx.lineTo(x, y + height);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
    }

    /* ==========================================================================
       EVENT LISTENERS
       ========================================================================== */

    function setupEventListeners() {
        // Optimize Button
        elements.btnOptimize.addEventListener("click", runOptimization);

        // Close Results Button
        elements.btnCloseResults.addEventListener("click", () => {
            elements.resultsPanel.classList.add("hidden");
        });

        // Chart Tabs
        elements.tabBarChart.addEventListener("click", () => {
            state.currentChartType = "bar";
            elements.tabBarChart.classList.add("active");
            elements.tabConvergenceChart.classList.remove("active");
            elements.chartTitle.textContent = "Route Cost Comparison";
            renderAnalyticsChart();
        });

        elements.tabConvergenceChart.addEventListener("click", () => {
            state.currentChartType = "convergence";
            elements.tabConvergenceChart.classList.add("active");
            elements.tabBarChart.classList.remove("active");
            elements.chartTitle.textContent = "ACO Convergence Curve";
            renderAnalyticsChart();
        });

        // Layer Toggles
        elements.chkShowOptimized.addEventListener("change", (e) => {
            if (state.mapProvider === "google" && state.optimizedPolylineLayer) {
                state.optimizedPolylineLayer.setVisible(e.target.checked);
            } else if (state.mapProvider === "leaflet" && state.optimizedPolylineLayer) {
                if (e.target.checked) state.map.addLayer(state.optimizedPolylineLayer);
                else state.map.removeLayer(state.optimizedPolylineLayer);
            }
        });

        elements.chkShowBaseline.addEventListener("change", (e) => {
            if (state.mapProvider === "google" && state.baselinePolylineLayer) {
                state.baselinePolylineLayer.setVisible(e.target.checked);
            } else if (state.mapProvider === "leaflet" && state.baselinePolylineLayer) {
                if (e.target.checked) state.map.addLayer(state.baselinePolylineLayer);
                else state.map.removeLayer(state.baselinePolylineLayer);
            }
        });

        // Presets Dropdown
        elements.presetSelect.addEventListener("change", (e) => {
            if (e.target.value) {
                loadPreset(e.target.value);
            }
        });

        // Add Stop Button
        elements.btnAddStop.addEventListener("click", () => {
            if (state.stops.length >= state.maxStops) {
                showError(`Maximum ${state.maxStops} stops reached.`);
                return;
            }
            let centerLat = state.defaultCenter.lat;
            let centerLng = state.defaultCenter.lng;

            if (state.stops.length > 0) {
                const last = state.stops[state.stops.length - 1];
                centerLat = last.lat + 0.02 * (Math.random() - 0.5);
                centerLng = last.lng + 0.02 * (Math.random() - 0.5);
            }
            addNewStop(centerLat, centerLng);
        });

        // Reset All Stops Button
        elements.btnResetStops.addEventListener("click", () => {
            if (state.stops.length === 0) return;
            if (confirm("Reset all stops and markers?")) {
                resetAllStops();
            }
        });

        // Reset Hyperparameters
        elements.btnResetParams.addEventListener("click", () => {
            document.getElementById("param-ants").value = "20";
            document.getElementById("param-iterations").value = "40";
            document.getElementById("param-alpha").value = "1.0";
            document.getElementById("param-beta").value = "2.5";
            document.getElementById("param-evaporation").value = "0.2";
            document.getElementById("param-q").value = "100.0";
            document.getElementById("param-seed").value = "";
        });

        // Info Modal
        elements.btnInfo.addEventListener("click", () => {
            elements.infoModal.classList.remove("hidden");
        });
        elements.btnCloseModal.addEventListener("click", () => {
            elements.infoModal.classList.add("hidden");
        });
        window.addEventListener("click", (e) => {
            if (e.target === elements.infoModal) {
                elements.infoModal.classList.add("hidden");
            }
        });
    }

    /* ==========================================================================
       UI UTILITY HELPERS
       ========================================================================== */

    function showSpinner(msg = "Optimizing Route...") {
        elements.spinnerText.textContent = msg;
        elements.statusSpinner.classList.remove("hidden");
        elements.btnOptimize.disabled = true;
    }

    function hideSpinner() {
        elements.statusSpinner.classList.add("hidden");
        elements.btnOptimize.disabled = false;
    }

    function showError(msg) {
        elements.errorMessage.textContent = msg;
        elements.errorMessage.classList.remove("hidden");
    }

    function hideError() {
        elements.errorMessage.classList.add("hidden");
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Expose controller methods to window
    window.APP_CONTROLLER = {
        state: state,
        runOptimization: runOptimization,
        addNewStop: addNewStop,
        removeStop: removeStop,
        moveStop: moveStop,
        resetAllStops: resetAllStops,
        loadPreset: loadPreset,
        decodePolyline: decodePolyline,
        renderAnalyticsChart: renderAnalyticsChart,
    };

    document.addEventListener("DOMContentLoaded", init);
})();
