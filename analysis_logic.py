import pandas as pd
import plotly.express as px
from datetime import timedelta

class DashboardLogic:
    """
    Handles all backend data processing and visualization generation for the dashboard.
    """
    def __init__(self, features_filepath: str, events_filepath: str):
        try:
            self.df_features = pd.read_csv(features_filepath)
            self.df_features['date'] = pd.to_datetime(self.df_features['date'])
            print("Successfully loaded the daily features dataset.")
        except FileNotFoundError:
            self.df_features = pd.DataFrame()
            
        try:
            self.df_events = pd.read_parquet(events_filepath)
            print("Successfully loaded the raw events dataset.")
        except FileNotFoundError:
            self.df_events = pd.DataFrame()
        
        self.baselines = {}

    def calculate_baselines(self, learning_period_days: int = 14):
        if self.df_features.empty: return
        print(f"Calculating baselines using a {learning_period_days}-day learning period...")
        baseline_features = ['sleep_duration_hours', 'sleep_fragmentation_index', 'total_hours_out_of_room', 'nightly_bathroom_visits', 'restlessness_count', 'total_time_in_bed_24h']
        for resident_id in self.df_features['resident_id'].unique():
            df_res = self.df_features[self.df_features['resident_id'] == resident_id]
            learning_data = df_res.head(learning_period_days)
            baseline_stats = {}
            for feature in baseline_features:
                mean = learning_data[feature].mean(); std = learning_data[feature].std()
                min_std = 0.1 * mean if mean > 0 else 0.1
                baseline_stats[feature] = {'mean': mean, 'std': max(std, min_std)}
            self.baselines[resident_id] = baseline_stats
        print("Baseline calculation complete.")

    # --- REVISED to accept a specific time window ---
    def get_daily_timeline_figure(self, resident_id: str, start_time: pd.Timestamp, end_time: pd.Timestamp):
        """
        Generates the 'Day in the Life' Gantt chart for a specific time window.
        """
        if self.df_events.empty: return go.Figure()

        df_window = self.df_events[
            (self.df_events['resident_id'] == resident_id) & 
            (self.df_events['timestamp'] >= start_time) &
            (self.df_events['timestamp'] <= end_time)
        ].copy()
        
        state_change_events = ['Present', 'NotPresent', 'Presence', 'NoPresence', 'ClosedToOpen']
        df_state_changes = df_window[df_window['event_type'].isin(state_change_events)].sort_values('timestamp')

        if df_state_changes.empty: return go.Figure().update_layout(title_text=f"No activity data for {resident_id} in this window.")

        activities = []
        # Determine the initial state at the start of the window
        initial_state_events = self.df_events[(self.df_events['resident_id'] == resident_id) & (self.df_events['timestamp'] < start_time)].sort_values('timestamp', ascending=False)
        current_location = "In Room" # Default
        if not initial_state_events.empty:
            last_event = initial_state_events.iloc[0]
            if last_event['sensor_type'] == 'bed_sensor': current_location = 'In Bed' if last_event['event_type'] == 'Present' else 'In Room'
            # Add more logic if needed for other initial states
        
        last_timestamp = start_time

        for _, row in df_state_changes.iterrows():
            new_location = current_location
            if row['sensor_type'] == 'bed_sensor': new_location = 'In Bed' if row['event_type'] == 'Present' else 'In Room'
            elif 'bath' in row['sensor_id']: new_location = 'In Bathroom' if row['event_type'] == 'Presence' else 'In Room'
            elif 'door' in row['sensor_id'] and row['event_type'] == 'ClosedToOpen':
                if current_location == 'In Room': new_location = 'Out of Room'
                elif current_location == 'Out of Room': new_location = 'In Room'
            
            if new_location != current_location:
                activities.append({'Task': current_location, 'Start': last_timestamp, 'Finish': row['timestamp'], 'Resource': current_location})
                current_location = new_location
                last_timestamp = row['timestamp']

        activities.append({'Task': current_location, 'Start': last_timestamp, 'Finish': end_time, 'Resource': current_location})

        df_plot = pd.DataFrame(activities)
        color_map = {"In Bed": "blue", "In Bathroom": "red", "Out of Room": "green", "In Room": "orange"}

        fig = px.timeline(df_plot, x_start="Start", x_end="Finish", y="Resource", color="Resource",
                          color_discrete_map=color_map, title=f"Activity Timeline for {resident_id}")
        fig.update_layout(xaxis_title="Time", yaxis_title="Location", showlegend=True)
        fig.update_yaxes(categoryorder='array', categoryarray=['In Bed', 'In Bathroom', 'In Room', 'Out of Room'])
        
        return fig