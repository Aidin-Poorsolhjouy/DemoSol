import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
from datetime import date, timedelta, datetime
import pandas as pd
import plotly.graph_objects as go
import os
import json

from analysis_logic import DashboardLogic

# ==============================================================================
# Final Polished Dashboard Application
# ==============================================================================

# --- 1. Initialization ---
app = dash.Dash(__name__, title='Solvae', 
    update_title=None)
server = app.server
LEARNING_PERIOD_DAYS = 14
logic_engine = DashboardLogic(
    features_filepath='data/daily_features.csv',
    events_filepath='data/all_events.parquet'
)
logic_engine.calculate_baselines()

# --- 2. App Layout ---
app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif', 'padding': '20px',  'margin': 'auto'}, children=[
    html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[html.Div(children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center'}, children=[html.Img(src=app.get_asset_url('solvae-logo.png'), style={'height': '50px', 'marginRight': '20px'}),
        html.H2("Solvae Caregiver Dashboard", style={'textAlign': 'left', 'color': '#333', 'marginTo': '0px'})]),
        
    html.P("Proactive Morning Summary", style={'textAlign': 'left', 'color': '#666', 'marginBottom': '0',  'marginTop': '5px'})]),
    

    html.Div(style={'backgroundColor': '#f9f9f9', 'padding': '15px', 'borderRadius': '5px', 'marginBottom': '10px'}, children=[
        html.Label("Select Summary Date:", style={'fontWeight': 'bold', 'marginRight': '10px'}),
        dcc.DatePickerSingle(
            id='date-picker',
            min_date_allowed=logic_engine.df_features['date'].min().date(),
            max_date_allowed=logic_engine.df_features['date'].max().date(),
            initial_visible_month=logic_engine.df_features['date'].max().date(),
            date=logic_engine.df_features['date'].max().date(),
            display_format='YYYY-MM-DD',
        )
    ])]),
    

    dcc.Store(id='selected-resident-store'),
    dcc.Store(id='feedback-context-store'),
    html.Div(id='dashboard-content'),

    # --- Feedback Modal with Modern Styling ---
    html.Div(id='feedback-modal', style={'display': 'none', 'position': 'fixed', 'zIndex': '100', 'left': '0', 'top': '0', 'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.4)'}, children=[
        html.Div(style={'backgroundColor': '#fefefe', 'margin': '15% auto', 'padding': '20px', 'border': '1px solid #888', 'width': '50%', 'borderRadius': '8px', 'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)'}, children=[
            html.H4("Provide Feedback", style={'marginBottom': '20px'}),
            dcc.Textarea(id='feedback-textarea', placeholder="Why was this alert helpful or not helpful? (Optional)", style={'width': '100%', 'height': 100, 'borderRadius': '4px', 'border': '1px solid #ccc'}),
            html.Div(style={'marginTop': '20px', 'textAlign': 'right'}, children=[
                html.Button('Cancel', id='cancel-feedback-btn', n_clicks=0, style={'backgroundColor': '#6c757d', 'color': 'white', 'border': 'none', 'padding': '10px 20px', 'borderRadius': '5px', 'cursor': 'pointer', 'marginRight': '10px'}),
                html.Button('Submit Feedback', id='submit-feedback-btn', n_clicks=0, style={'backgroundColor': '#007bff', 'color': 'white', 'border': 'none', 'padding': '10px 20px', 'borderRadius': '5px', 'cursor': 'pointer'})
            ])
        ])
    ])
])


# --- 3. Main Interactive Callback ---
@app.callback(
    Output('dashboard-content', 'children'),
    [Input('date-picker', 'date'), Input('selected-resident-store', 'data')]
)
def update_dashboard(selected_date_str, stored_resident_data):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'No trigger'

    if not selected_date_str: return html.P("Please select a date.")
    selected_date = pd.to_datetime(selected_date_str)

    min_data_date = logic_engine.df_features['date'].min()
    if selected_date < min_data_date + timedelta(days=LEARNING_PERIOD_DAYS):
        return html.Div([
            html.H3("Alerts & Insights", style={'borderBottom': '2px solid #333', 'paddingBottom': '5px'}),
            html.P(f"No alerts available. The system is in a baseline learning period until {(min_data_date + timedelta(days=LEARNING_PERIOD_DAYS)).strftime('%Y-%m-%d')}.")
        ])


    # selected_resident_id = stored_resident_data['resident_id'] if stored_resident_data else None

    selected_resident_id = None
    if trigger_id != 'date-picker' and stored_resident_data:
        selected_resident_id = stored_resident_data.get('resident_id')


    all_alerts = []
    for resident_id, baseline in logic_engine.baselines.items():
        day_data = logic_engine.df_features[(logic_engine.df_features['resident_id'] == resident_id) & (logic_engine.df_features['date'] == selected_date)]
        if day_data.empty: continue
        day_data = day_data.iloc[0]
        
        if day_data['nightly_bathroom_visits'] > baseline['nightly_bathroom_visits']['mean'] + 2 * baseline['nightly_bathroom_visits']['std']:
            all_alerts.append({'resident_id': resident_id, 'severity': 'High', 'category': 'UTI Risk', 'title': 'High Nightly Bathroom Activity', 'reason': f"{int(day_data['nightly_bathroom_visits'])} visits (vs. ~{baseline['nightly_bathroom_visits']['mean']:.1f})", 'recommendation': 'Consider UTI screening.'})
        if day_data['restlessness_count'] > baseline['restlessness_count']['mean'] + 2 * baseline['restlessness_count']['std']:
            all_alerts.append({'resident_id': resident_id, 'severity': 'Medium', 'category': 'Sleep', 'title': 'Restless Night', 'reason': f"{int(day_data['restlessness_count'])} events (vs. ~{baseline['restlessness_count']['mean']:.1f})", 'recommendation': 'Consider delaying non-essential morning care.'})
        if day_data['total_hours_out_of_room'] < baseline['total_hours_out_of_room']['mean'] - 1.5 * baseline['total_hours_out_of_room']['std']:
            all_alerts.append({'resident_id': resident_id, 'severity': 'Medium', 'category': 'Activity', 'title': 'Reduced Social Activity', 'reason': f"{day_data['total_hours_out_of_room']:.1f}h out (vs. ~{baseline['total_hours_out_of_room']['mean']:.1f}h)", 'recommendation': 'Encourage social activities.'})

        # if day_data['nightly_bathroom_visits'] > baseline['nightly_bathroom_visits']['mean'] + 2 * baseline['nightly_bathroom_visits']['std']: all_alerts.append({'resident_id': resident_id, 'severity': 'High', 'category': 'UTI Risk', 'title': 'High Nightly Bathroom Activity', 'reason': f"{int(day_data['nightly_bathroom_visits'])} visits (vs. ~{baseline['nightly_bathroom_visits']['mean']:.1f})", 'recommendation': 'Consider UTI screening'})
        # if day_data['restlessness_count'] > baseline['restlessness_count']['mean'] + 2 * baseline['restlessness_count']['std']: all_alerts.append({'resident_id': resident_id, 'severity': 'Medium', 'category': 'Sleep', 'title': 'Restless Night', 'reason': f"{int(day_data['restlessness_count'])} events (vs. ~{baseline['restlessness_count']['mean']:.1f})", 'recommendation': 'Consider delaying non-essential morning care'})
        # if day_data['total_hours_out_of_room'] < baseline['total_hours_out_of_room']['mean'] - 1.5 * baseline['total_hours_out_of_room']['std']: all_alerts.append({'resident_id': resident_id, 'severity': 'Medium', 'category': 'Activity', 'title': 'Reduced Social Activity', 'reason': f"{day_data['total_hours_out_of_room']:.1f}h out (vs. ~{baseline['total_hours_out_of_room']['mean']:.1f}h)", 'recommendation': 'Encourage social activities'})
    def create_alert_card(alert_data):
        category_colors = {'UTI Risk': '#dc3545', 'Sleep': '#ffc107', 'Activity': '#17a2b8'}
        card_color = category_colors.get(alert_data['category'], '#6c757d')
        style = {'border': f'2px solid {card_color}', 'padding': '15px', 'marginBottom': '10px', 'backgroundColor': '#fff', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'cursor': 'pointer', 'position': 'relative', 'minHeight': '50px'}
        if alert_data['resident_id'] == selected_resident_id: style['boxShadow'] = f'0 0 15px {card_color}'; style['transform'] = 'scale(1.02)'
        alert_instance_id = f"{alert_data['resident_id']}_{alert_data['category']}_{selected_date.strftime('%Y-%m-%d')}"
        return html.Div(id={'type': 'alert-card', 'index': alert_data['resident_id']}, style=style, children=[
            html.H5(f"{alert_data['title']} - {alert_data['resident_id']}", style={'margin': 0, 'color': card_color}),
            html.P(f"Reason: {alert_data['reason']}", style={'margin': '5px 0'}),
            html.P(f"{alert_data['recommendation']}", style={'fontWeight': 'bold', 'margin': '5px 0'}),
            html.Div(id={'type': 'feedback-container', 'index': alert_instance_id}, style={'position': 'absolute', 'bottom': '10px', 'right': '10px', 'display': 'flex', 'alignItems': 'center'}, children=[
                html.Button('✓', id={'type': 'feedback-btn', 'index': alert_instance_id, 'value': 'helpful'}, style={'cursor': 'pointer', 'marginRight': '5px', 'border': '1px solid green', 'color': 'green', 'background': 'white', 'borderRadius': '50%', 'width': '30px', 'height': '30px'}),
                html.Button('✗', id={'type': 'feedback-btn', 'index': alert_instance_id, 'value': 'not-helpful'}, style={'cursor': 'pointer', 'border': '1px solid red', 'color': 'red', 'background': 'white', 'borderRadius': '50%', 'width': '30px', 'height': '30px'}),
                html.Div(id={'type': 'feedback-msg', 'index': alert_instance_id}, style={'marginLeft': '10px', 'fontSize': '12px', 'color': 'green'})
            ])
        ])
    high_priority_cards = [create_alert_card(a) for a in all_alerts if a['severity'] == 'High']
    medium_priority_cards = [create_alert_card(a) for a in all_alerts if a['severity'] == 'Medium']
    timeline_figure = go.Figure().update_layout(title_text="Click on an alert card to view the resident's detailed timeline.")
    if selected_resident_id:
        end_time = selected_date.replace(hour=8, minute=0); start_time = end_time - timedelta(days=1, hours=2)
        timeline_figure = logic_engine.get_daily_timeline_figure(selected_resident_id, start_time, end_time)
    return html.Div([
        html.H3("Alerts & Insights", style={'borderBottom': '2px solid #333', 'paddingBottom': '5px'}),
        html.Div(children=high_priority_cards + medium_priority_cards if (high_priority_cards or medium_priority_cards) else [html.P("No significant deviations detected for this day.")], style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fill, minmax(350px, 1fr))', 'gap': '10px'}),
        html.Div([html.H3("Resident Activity Timeline", style={'marginTop': '10px', 'borderBottom': '2px solid #6c757d', 'paddingBottom': '5px'}), dcc.Graph(figure=timeline_figure)])
    ])

# --- 4. Callback for Storing Selected Resident ID ---
@app.callback(Output('selected-resident-store', 'data'), Input({'type': 'alert-card', 'index': dash.dependencies.ALL}, 'n_clicks'), prevent_initial_call=True)
def store_clicked_resident_id(n_clicks):
    ctx = dash.callback_context
    if not ctx.triggered_id: raise dash.exceptions.PreventUpdate
    return {'resident_id': ctx.triggered_id['index']}

# --- 5. Callback to Open Feedback Modal ---
@app.callback(
    [Output('feedback-modal', 'style'), Output('feedback-context-store', 'data')],
    Input({'type': 'feedback-btn', 'index': dash.dependencies.ALL, 'value': dash.dependencies.ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def open_feedback_modal(n_clicks):
    ctx = dash.callback_context
    if not ctx.triggered_id or not any(n_clicks): raise dash.exceptions.PreventUpdate
    button_id = ctx.triggered_id
    context_data = {'alert_instance_id': button_id['index'], 'feedback_value': button_id['value']}
    modal_style = {'display': 'block', 'position': 'fixed', 'zIndex': '100', 'left': '0', 'top': '0', 'width': '100%', 'height': '100%', 'backgroundColor': 'rgba(0,0,0,0.4)'}
    return modal_style, context_data

# --- 6. Callback to Submit or Cancel Feedback ---
@app.callback(
    [Output('feedback-modal', 'style', allow_duplicate=True),
     Output('feedback-textarea', 'value'),
     Output({'type': 'feedback-container', 'index': dash.dependencies.ALL}, 'children')],
    [Input('submit-feedback-btn', 'n_clicks'), Input('cancel-feedback-btn', 'n_clicks')],
    [State('feedback-context-store', 'data'), State('feedback-textarea', 'value')],
    prevent_initial_call=True
)
def submit_or_cancel_feedback(submit_clicks, cancel_clicks, context_data, feedback_text):
    ctx = dash.callback_context
    button_clicked = ctx.triggered_id
    
    feedback_container_children = [dash.no_update] * len(ctx.outputs_grouping[2])

    if button_clicked == 'submit-feedback-btn' and context_data:
        log_entry = {'timestamp': datetime.now().isoformat(), 'alert_instance_id': context_data['alert_instance_id'], 'feedback': context_data['feedback_value'], 'comment': feedback_text}
        log_file = 'feedback_log.csv'
        df_log = pd.DataFrame([log_entry])
        df_log.to_csv(log_file, mode='a', header=not os.path.exists(log_file), index=False)
        print(f"Feedback logged: {log_entry}")

        # Find the correct feedback container to update
        for i, output in enumerate(ctx.outputs_grouping[2]):
            if output['id']['index'] == context_data['alert_instance_id']:
                # Replace the buttons with the "Saved" message
                feedback_container_children[i] = html.Div("✓ Saved", style={'color': 'green'})
                break

    # Close the modal and reset the textarea
    modal_style = {'display': 'none'}
    reset_textarea = ''
    return modal_style, reset_textarea, feedback_container_children


# --- 6. Run the App ---
if __name__ == '__main__':
    app.run_server(debug=True)