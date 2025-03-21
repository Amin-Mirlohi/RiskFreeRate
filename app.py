from flask import Flask, render_template, request
import pandas as pd
import numpy as np
from datetime import datetime
from scipy.optimize import curve_fit
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
import io
from flask import jsonify

app = Flask(__name__)

# Load your data
df = pd.read_csv('combined_subset_20250312_101840.csv')
df['Maturity'] = pd.to_datetime(df['Maturity'], errors='coerce')

# NSS Function
def nss(t, beta0, beta1, beta2, beta3, tau1, tau2):
    term1 = beta0
    term2 = beta1 * ((1 - np.exp(-t / tau1)) / (t / tau1))
    term3 = beta2 * (((1 - np.exp(-t / tau1)) / (t / tau1)) - np.exp(-t / tau1))
    term4 = beta3 * (((1 - np.exp(-t / tau2)) / (t / tau2)) - np.exp(-t / tau2))
    return term1 + term2 + term3 + term4

# Maturities for NSS evaluation table
NSS_MATURITIES = [1/12, 3/12, 6/12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20]
NSS_LABELS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "4Y", "5Y",
              "6Y", "7Y", "8Y", "9Y", "10Y", "15Y", "20Y"]
@app.route('/', methods=['GET', 'POST'])
def home():
    countries = sorted(df['Country_Name'].dropna().unique())
    selected_country = selected_date = plot_b64 = error_message = user_specific_maturity = None
    calculated = nss_params = nss_values = specific_maturity_yield = None

    if request.method == 'POST':
        selected_country = request.form.get('country')
        selected_date = request.form.get('date')
        user_specific_maturity = request.form.get('specific_maturity')

        if selected_country and selected_date:
            selected_datetime = pd.to_datetime(selected_date, errors='coerce')
            df_country = df[(df['Country_Name'] == selected_country)].dropna(subset=['Maturity', 'Indicative yield, %']).copy()
            df_country['Yearfrac'] = ((df_country['Maturity'] - selected_datetime).dt.days) / 365
            df_filtered = df_country[(df_country['Yearfrac'] > 0.25) & (df_country['Indicative yield, %'] <= 1)].copy()

            if df_filtered.empty or len(df_filtered) < 4:
                error_message = "Insufficient suitable bonds for NSS curve fitting (need at least 4 bonds)."
            else:
                # Closest bond at 10 years by default
                target_year = 10
                df_filtered['days_from_target'] = abs(df_filtered['Yearfrac'] - target_year)
                closest_bond = df_filtered.sort_values('days_from_target').iloc[0]

                calculated = {
                    'country': selected_country,
                    'chosen_date': selected_date,
                    'target_year': target_year,
                    'maturity': closest_bond['Maturity'].strftime("%Y-%m-%d"),
                    'bond_name': closest_bond['Issue'],
                    'ytm': round(closest_bond['Indicative yield, %']*100,4),
                    'isin': closest_bond['ISIN']
                }

                # NSS Curve fit
                xdata, ydata = df_filtered['Yearfrac'], df_filtered['Indicative yield, %']
                try:
                    init_guess = [0.03, -0.02, 0.02, 0.01, 1.5, 3.0]
                    params, _ = curve_fit(nss, xdata, ydata, p0=init_guess, maxfev=10000)

                    nss_params = dict(zip(
                        ['Beta0', 'Beta1', 'Beta2', 'Beta3', 'Tau1', 'Tau2'],
                        [round(p,4) for p in params]
                    ))

                    # NSS Values at predefined maturities
                    nss_yields = [round(nss(t, *params)*100, 3) for t in NSS_MATURITIES]
                    nss_values = list(zip(NSS_LABELS, nss_yields))

                    # Check if user specified a particular maturity
                    if user_specific_maturity:
                        try:
                            specific_maturity_float = float(user_specific_maturity)
                            specific_maturity_yield = round(nss(specific_maturity_float, *params)*100, 3)
                        except ValueError:
                            error_message = "Specific maturity entered is invalid. Please enter a number."

                    # Generate Plot
                    fig, ax = plt.subplots(figsize=(10,5))
                    plot_x = np.linspace(0, max(20,max(xdata)+1), 200)
                    ax.plot(plot_x, nss(plot_x, *params)*100, 'navy', label='NSS Fit')
                    ax.scatter(xdata, ydata*100, c='crimson', label='Bond Data')
                    ax.set_xlabel('Years to Maturity')
                    ax.set_ylabel('Yield (%)')
                    ax.set_title(f'NSS Curve - {selected_country}', fontsize=14)
                    ax.legend()
                    ax.grid(True)

                    buf = io.BytesIO()
                    plt.savefig(buf, format='png', bbox_inches='tight')
                    plt.close(fig)
                    buf.seek(0)
                    plot_b64 = base64.b64encode(buf.getvalue()).decode('utf8')

                except Exception as e:
                    error_message = f"Curve fitting failed: {str(e)}"
        else:
            error_message = "Please fill both fields."

    return render_template('index.html', countries=countries, calculated=calculated,
                           selected_country=selected_country, selected_date=selected_date,
                           nss_params=nss_params, nss_plot_base64=plot_b64,
                           nss_values=nss_values, error_message=error_message,
                           user_specific_maturity=user_specific_maturity,
                           specific_maturity_yield=specific_maturity_yield)

@app.route('/api/risk_free_rate', methods=['GET'])
def api_risk_free_rate():
    country = request.args.get('country')
    date_str = request.args.get('date', None)
    specific_maturity = request.args.get('specific_maturity', None)

    if not country:
        return jsonify({"error": "country parameter is required"}), 400

    df_country = df[df['Country_Name'] == country].dropna(subset=['Maturity', 'Indicative yield, %']).copy()
    if df_country.empty:
        return jsonify({"error": "No data available for the selected country"}), 404

    # Handle Date
    if date_str:
        selected_datetime = pd.to_datetime(date_str, errors='coerce')
        if pd.isnull(selected_datetime):
            return jsonify({"error": "Invalid date format. Expected YYYY-MM-DD"}), 400
    else:
        selected_datetime = pd.Timestamp.today()

    df_country['Yearfrac'] = ((df_country['Maturity'] - selected_datetime).dt.days) / 365
    df_filtered = df_country[(df_country['Yearfrac'] > 0.25) & (df_country['Indicative yield, %'] <= 1)].copy()

    if df_filtered.empty or len(df_filtered) < 4:
        return jsonify({"error": "Insufficient suitable bonds for NSS curve fitting (requires at least 4 bonds)."}), 400

    # NSS Curve fitting
    xdata, ydata = df_filtered['Yearfrac'], df_filtered['Indicative yield, %']
    init_guess = [0.03, -0.02, 0.02, 0.01, 1.5, 3.0]

    try:
        params, _ = curve_fit(nss, xdata, ydata, p0=init_guess, maxfev=10000)
        nss_params = dict(zip(['Beta0', 'Beta1', 'Beta2', 'Beta3', 'Tau1', 'Tau2'], params))

        # Calculated NSS values for predefined maturities
        nss_results = {
            label: round(nss(t, *params) * 100, 3)
            for label, t in zip(NSS_LABELS, NSS_MATURITIES)
        }

        # Specific maturity calculation if provided
        specific_maturity_result = None
        if specific_maturity:
            try:
                specific_maturity_float = float(specific_maturity)
                specific_maturity_result = round(nss(specific_maturity_float, *params) * 100, 3)
            except ValueError:
                return jsonify({"error": "specific_maturity must be a numeric value"}), 400
        
        response = {
            "country": country,
            "date_used": selected_datetime.strftime('%Y-%m-%d'),
            "nss_parameters": {key: round(value, 6) for key, value in nss_params.items()},
            "nss_yields": nss_results
        }

        if specific_maturity:
            response["specific_maturity"] = {
                "years": specific_maturity_float,
                "yield_percent": specific_maturity_result
            }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": f"Curve fitting failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)