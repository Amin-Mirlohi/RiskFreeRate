from flask import Flask, render_template, request
import pandas as pd
import numpy as np
from datetime import datetime
from scipy.optimize import curve_fit
import matplotlib
matplotlib.use('Agg')  # Set backend to Agg BEFORE pyplot import
import matplotlib.pyplot as plt
import os

app = Flask(__name__)

# Load data once
df = pd.read_csv('combined_subset_20250312_101840.csv')
df['Maturity'] = pd.to_datetime(df['Maturity'], errors='coerce')

def nss(t, beta0, beta1, beta2, beta3, tau1, tau2):
    term1 = beta0
    term2 = beta1 * ((1 - np.exp(-t / tau1)) / (t / tau1))
    term3 = beta2 * (((1 - np.exp(-t / tau1)) / (t / tau1)) - np.exp(-t / tau1))
    term4 = beta3 * (((1 - np.exp(-t / tau2)) / (t / tau2)) - np.exp(-t / tau2))
    return term1 + term2 + term3 + term4

@app.route('/', methods=['GET', 'POST'])
def home():
    country_list = sorted(df['Country_Name'].dropna().unique().tolist())
    selected_country = ''
    selected_date = ''
    calculated = None
    nss_params = None
    nss_plot_url = None
    error_message = None

    if request.method == 'POST':
        selected_country = request.form.get('country')
        selected_date = request.form.get('date')

        if selected_country and selected_date:
            selected_datetime = pd.to_datetime(selected_date, errors='coerce')

            df_country = df[
                (df['Country_Name'] == selected_country) &
                (~df['Maturity'].isna()) &
                (~df['Indicative yield, %'].isna())
            ].copy()

            if df_country.empty:
                error_message = "No suitable bond data found for selection."
            else:
                df_country['Yearfrac'] = ((df_country['Maturity'] - selected_datetime).dt.days) / 365

                # Explicitly copy to avoid the warning
                df_filtered = df_country.loc[
                    (df_country['Yearfrac'] > 0.25) & 
                    (df_country['Indicative yield, %'] <= 1)
                ].copy()

                # Closest bond to exactly 10 years maturity
                df_filtered.loc[:, 'days_from_10y'] = (df_filtered['Yearfrac'] - 10).abs()
                closest_bond = df_filtered.sort_values('days_from_10y').head(1).iloc[0]

                calculated = {
                    'country': selected_country,
                    'chosen_date': selected_date,
                    'maturity': closest_bond['Maturity'].strftime("%Y-%m-%d"),
                    'bond_name': closest_bond['Issue'],
                    'ytm': round(closest_bond['Indicative yield, %'] * 100, 4),
                    'isin': closest_bond['ISIN']
                }

                # NSS Curve Fit
                if len(df_filtered) >= 4:
                    xdata = df_filtered['Yearfrac'].values
                    ydata = df_filtered['Indicative yield, %'].values
                    init_guess = [0.03, -0.02, 0.02, 0.01, 2.0, 5.0]

                    try:
                        params, _ = curve_fit(nss, xdata, ydata, p0=init_guess, maxfev=10000)
                        nss_params = {
                            'Beta0': round(params[0], 4),
                            'Beta1': round(params[1], 4),
                            'Beta2': round(params[2], 4),
                            'Beta3': round(params[3], 4),
                            'Tau1': round(params[4], 4),
                            'Tau2': round(params[5], 4)
                        }

                        plt.figure(figsize=(8,4))
                        plot_x = np.linspace(min(xdata), max(xdata), 100)
                        plt.plot(plot_x, nss(plot_x, *params)*100, 'b-', label='NSS Fit')
                        plt.scatter(xdata, ydata*100, c='red', label='Actual')
                        plt.xlabel('Years to Maturity')
                        plt.ylabel('Yield (%)')
                        plt.title(f'NSS Yield Curve - {selected_country}')
                        plt.grid(True)
                        plt.legend()

                        plot_dir = os.path.join('static', 'plots')
                        if not os.path.exists(plot_dir):
                            os.makedirs(plot_dir)

                        plot_filename = f'nss_{selected_country}_{selected_date}.png'
                        plt.savefig(os.path.join(plot_dir, plot_filename), bbox_inches='tight')
                        plt.close()

                        nss_plot_url = os.path.join('plots', plot_filename)

                    except Exception as e:
                        error_message = f"Curve fitting issue: {str(e)}"
                else:
                    error_message = "Insufficient bonds to fit NSS curve (minimum 4 needed)."

        else:
            error_message = "Please select both country and date."

    return render_template('index.html', 
                           countries=country_list,
                           calculated=calculated,
                           selected_country=selected_country, 
                           selected_date=selected_date,
                           error_message=error_message,
                           nss_params=nss_params,
                           nss_plot_url=nss_plot_url)

if __name__ == '__main__':
    app.run(debug=True)