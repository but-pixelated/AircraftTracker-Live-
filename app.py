import gradio as gr
import folium
from folium import plugins
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from datetime import datetime
import time
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
USERNAME = os.getenv("ID_AUTH")
PASSWORD = os.getenv("PW_AUTH")
 
class OpenSkyApi:
    def __init__(self, username=None, password=None):
        self.auth = HTTPBasicAuth(username, password) if username and password else None
        self.base_url = "https://opensky-network.org/api"
    
    def get_states(self, time_secs=0, icao24=None, bbox=None):
        """Retrieve state vectors for a given time."""
        params = {"time": int(time_secs) if time_secs else int(time.time())}
        
        if icao24:
            params["icao24"] = icao24
        if bbox:
            params.update({
                "lamin": bbox[0],
                "lamax": bbox[1],
                "lomin": bbox[2],
                "lomax": bbox[3]
            })
        
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/states/all",
                params=params,
                auth=self.auth,
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                return StateVector(response.json())
            elif response.status_code == 401:
                print("Authentication failed. Please check your environment variables ID_AUTH and PW_AUTH.")
                return None
            else:
                print(f"Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

class StateVector:
    def __init__(self, states_json):
        self.time = states_json.get('time', 0)
        self.states = []
        
        if states_json.get('states'):
            for state in states_json['states']:
                self.states.append(State(state))

class State:
    def __init__(self, state_array):
        self.icao24 = state_array[0]
        self.callsign = state_array[1]
        self.origin_country = state_array[2]
        self.time_position = state_array[3]
        self.last_contact = state_array[4]
        self.longitude = state_array[5]
        self.latitude = state_array[6]
        self.geo_altitude = state_array[7]
        self.on_ground = state_array[8]
        self.velocity = state_array[9]
        self.true_track = state_array[10]
        self.vertical_rate = state_array[11]
        self.sensors = state_array[12] if len(state_array) > 12 else None
        self.baro_altitude = state_array[13] if len(state_array) > 13 else None
        self.squawk = state_array[14] if len(state_array) > 14 else None
        self.spi = state_array[15] if len(state_array) > 15 else None
        self.position_source = state_array[16] if len(state_array) > 16 else None

api = OpenSkyApi(USERNAME, PASSWORD)

def get_states(bounds=None, max_retries=3):
    """Get current aircraft states from OpenSky Network with retry logic"""
    for attempt in range(max_retries):
        try:
            if bounds:
                bbox = (
                    bounds['lamin'],
                    bounds['lamax'],
                    bounds['lomin'],
                    bounds['lomax']
                )
                states = api.get_states(bbox=bbox)
            else:
                states = api.get_states()
            
            if states and states.states:
                return {'states': states.states}
            
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 60)
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            return None
                
        except Exception as e:
            print(f"Error fetching data: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return None
    return None

def create_monitoring_dashboard(states):
    """Create monitoring dashboard using Plotly"""
    if not states:
        return go.Figure()

    altitudes = [s.geo_altitude for s in states if s.geo_altitude is not None]
    speeds = [s.velocity for s in states if s.velocity is not None]
    countries = pd.Series([s.origin_country for s in states if s.origin_country])
    

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Altitude Distribution', 'Speed Distribution', 
                       'Aircraft by Country', 'Aircraft Categories'),
        specs=[
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "domain"}]
        ]
    )
    fig.add_trace(
        go.Histogram(x=altitudes, name="Altitude", marker_color='#4a90e2'),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Histogram(x=speeds, name="Speed", marker_color='#50C878'),
        row=1, col=2
    )
    
    top_countries = countries.value_counts().head(10)
    fig.add_trace(
        go.Bar(
            x=top_countries.index,
            y=top_countries.values,
            name="Countries",
            marker_color='#FF6B6B'
        ),
        row=2, col=1
    )

    categories = ['Commercial', 'Private', 'Military', 'Other']
    values = [40, 30, 20, 10] 
    fig.add_trace(
        go.Pie(
            labels=categories,
            values=values,
            name="Categories",
            marker=dict(colors=['#4a90e2', '#50C878', '#FF6B6B', '#FFD700'])
        ),
        row=2, col=2
    )

    fig.update_layout(
        height=800,
        showlegend=True,
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0.3)',
        plot_bgcolor='rgba(0,0,0,0.1)',
        margin=dict(l=50, r=50, t=50, b=50),
        font=dict(color='white'),
        legend=dict(
            bgcolor='rgba(0,0,0,0.3)',
            bordercolor='rgba(255,255,255,0.2)',
            borderwidth=1
        )
    )

    fig.update_xaxes(gridcolor='rgba(255,255,255,0.1)', zeroline=False)
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.1)', zeroline=False)

    for i in fig['layout']['annotations']:
        i['font'] = dict(size=12, color='white')

    return fig

def create_map(region="world"):
    """Create aircraft tracking map"""
    m = folium.Map(
        location=[30, 0],
        zoom_start=3,
        tiles='CartoDB dark_matter'
    )

    bounds = {
        "world": None,
        "europe": {"lamin": 35.0, "lomin": -15.0, "lamax": 60.0, "lomax": 40.0},
        "north_america": {"lamin": 25.0, "lomin": -130.0, "lamax": 50.0, "lomax": -60.0},
        "asia": {"lamin": 10.0, "lomin": 60.0, "lamax": 50.0, "lomax": 150.0}
    }

    data = get_states(bounds.get(region))
    
    if not data or not data['states']:
        return (
            m._repr_html_(), 
            create_monitoring_dashboard([]),
            "No data available. Please try again later."
        )

    states = data['states']
    heat_data = []

    for state in states:
        if state.latitude and state.longitude:
            lat, lon = state.latitude, state.longitude
            callsign = state.callsign if state.callsign else 'N/A'
            altitude = state.geo_altitude if state.geo_altitude else 'N/A'
            velocity = state.velocity if state.velocity else 'N/A'
            
            heat_data.append([lat, lon, 1])
            
            popup_content = f"""
            <div style="font-family: Arial; width: 200px;">
                <h4 style="color: #4a90e2;">Flight Information</h4>
                <p><b>Callsign:</b> {callsign}</p>
                <p><b>Altitude:</b> {altitude}m</p>
                <p><b>Velocity:</b> {velocity}m/s</p>
                <p><b>Origin:</b> {state.origin_country}</p>
            </div>
            """
            
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_content, max_width=300),
                icon=folium.DivIcon(
                    html=f'''
                        <div style="transform: rotate({state.true_track if state.true_track else 0}deg)">✈️</div>
                    ''',
                    icon_size=(20, 20)
                )
            ).add_to(m)

    plugins.HeatMap(heat_data, radius=15).add_to(m)
    
    total_aircraft = len(states)
    countries = len(set(s.origin_country for s in states if s.origin_country))
    avg_altitude = np.mean([s.geo_altitude for s in states if s.geo_altitude is not None]) if states else 0
    
    stats = f"""
    Real-time Statistics:
    • Total Aircraft: {total_aircraft}
    • Countries: {countries}
    • Average Altitude: {avg_altitude:.0f}m
    
    Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """

    return m._repr_html_(), create_monitoring_dashboard(states), stats

# csssssss 
custom_css = """
.gradio-container {
    background: linear-gradient(135deg, #1a1a1a, #2d2d2d) !important;
}
.gr-button {
    background: linear-gradient(135deg, #4a90e2, #357abd) !important;
    border: none !important;
    color: white !important;
}
.gr-button:hover {
    background: linear-gradient(135deg, #357abd, #4a90e2) !important;
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(74, 144, 226, 0.4) !important;
}
"""

# gradio ui
with gr.Blocks(css=custom_css) as demo:
    gr.HTML(
        """
        <h1 style="text-align: center; color: white;">Global Aircraft Tracker</h1>
        <h6 style="text-align: center; color: white;">Credits : Atharva</h6>
        <p style="text-align: center; color: #ccc;">Real-time tracking of aircraft worldwide</p>
        """
    )
    gr.HTML("""<a href="https://visitorbadge.io/status?path=https%3A%2F%2Fimmunobiotech-opensky.hf.space">
               <img src="https://api.visitorbadge.io/api/visitors?path=https%3A%2F%2Fimmunobiotech-opensky.hf.space&countColor=%23263759" />
               </a>""")        
    
    with gr.Row():
        region_select = gr.Dropdown(
            choices=["world", "europe", "north_america", "asia"],
            value="world",
            label="Select Region"
        )
        refresh_btn = gr.Button("🔄 Refresh")
    
    map_html = gr.HTML()
    stats_text = gr.Textbox(label="Statistics", lines=6)
    dashboard_plot = gr.Plot(label="Monitoring Dashboard")
    
    def update_map(region):
        try:
            return create_map(region)
        except Exception as e:
            print(f"Error updating map: {e}")
            return (
                "<p>Map loading failed. Please try again.</p>",
                go.Figure(),
                f"Error: {str(e)}"
            )
    
    refresh_btn.click(
        fn=update_map,
        inputs=[region_select],
        outputs=[map_html, dashboard_plot, stats_text]
    )
    
    region_select.change(
        fn=update_map,
        inputs=[region_select],
        outputs=[map_html, dashboard_plot, stats_text]
    )



if not USERNAME or not PASSWORD:
    print("Warning: Environment variables ID_AUTH and/or PW_AUTH are not set.")
    print("The application will run with anonymous access, which has lower rate limits.")

demo.launch(
    show_error=True,
    server_name="0.0.0.0",
    server_port=7860,
    share=False
)