from flask import Flask, render_template, request
import pandas as pd
from datetime import datetime

app = Flask(__name__)

# Load CSV file at startup
df = pd.read_csv('combined_subset_20250312_101840.csv')

# Ensure Maturity dates are properly parsed
df['Maturity'] = pd.to_datetime(df['Maturity'], errors='coerce')

@app.route('/', methods=['GET', 'POST'])
def home():
    country_list = sorted(df['Country_Name'].dropna().unique().tolist())
    calculated = None
    selected_country = ''
    selected_date = ''
    calculation_rows = None
    error_message = None

    if request.method == 'POST':
        selected_country = request.form.get('country')
        selected_date = request.form.get('date')

        if selected_country and selected_date:
            selected_datetime = pd.to_datetime(selected_date, errors='coerce')

            # Filter bonds carefully: Country match, Maturity valid, Yield present
            df_country = df[
                (df['Country_Name'] == selected_country) &
                (~df['Maturity'].isna()) &
                (~df['Indicative yield, %'].isna())
            ].copy()

            # Continue only if filtered data is not empty
            if not df_country.empty:
                df_country['days_from_10y'] = abs(
                    (df_country['Maturity'] - selected_datetime).dt.days - 365 * 10)

                # Check if rows are still present after adding 'days_from_10y'
                if not df_country.empty:
                    # Get closest bond without causing error
                    closest_bond = df_country.sort_values('days_from_10y').head(1)

                    if not closest_bond.empty:
                        bond = closest_bond.iloc[0]

                        calculated = {
                            'country': selected_country,
                            'chosen_date': selected_date,
                            'maturity': bond['Maturity'].strftime("%Y-%m-%d"),
                            'bond_name': bond['Issue'],
                            'ytm': round(bond['Indicative yield, %'] * 100, 4),
                            'isin': bond['ISIN']
                        }

                        # Rows used for calculation
                        calculation_rows = bond.to_frame().transpose().to_html(
                            classes='table', index=False)
                    else:
                        error_message = "No suitable bond found for the selected parameters."
                else:
                    error_message = "No bond maturity data available for selected country/date."
            else:
                error_message = "No bond data found matching the selected country or missing yields."
        else:
            error_message = "Please select both country and date."

    return render_template('index.html', 
                           countries=country_list,
                           calculated=calculated,
                           selected_country=selected_country, 
                           selected_date=selected_date,
                           calculation_rows=calculation_rows,
                           error_message=error_message)

if __name__ == '__main__':
    app.run(debug=True)