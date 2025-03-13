from flask import Flask, render_template, request
import pandas as pd
from datetime import datetime

app = Flask(__name__)

# Load CSV file at startup
df = pd.read_csv('combined_subset_20250312_101840.csv')

# Ensure Maturity is converted to datetime
df['Maturity'] = pd.to_datetime(df['Maturity'], errors='coerce')

@app.route('/', methods=['GET', 'POST'])
def home():
    country_list = sorted(df['Country_Name'].dropna().unique().tolist())
    calculated = None
    selected_country = None
    selected_date = None
    calculation_rows = None

    if request.method == 'POST':
        selected_country = request.form.get('country')
        selected_date = request.form.get('date')

        if selected_date:
            selected_datetime = pd.to_datetime(selected_date, errors='coerce')
            
            # Calculate difference close to 10 years (10*365 days) from selected date
            df_country = df[(df['Country_Name'] == selected_country)].dropna(subset=['Indicative yield, %'])
            # Add absolute days difference from 10-year period
            df_country['days_from_10y'] = abs((df_country['Maturity'] - selected_datetime).dt.days - 365*10)
            
            # Pick the bond closest to exactly 10-year horizon
            closest_bond = df_country.sort_values(by=['days_from_10y']).iloc[0]

            calculated = {
                'country': selected_country,
                'chosen_date': selected_date,
                'maturity': closest_bond['Maturity'].strftime("%Y-%m-%d"),
                'bond_name': closest_bond['Issue'], 
                'ytm': float(closest_bond['Indicative yield, %']*100),
                'isin': closest_bond['ISIN']
            }
            
            # Rows used for calculation
            calculation_rows = closest_bond.to_frame().transpose().to_html(classes='table', index=False)
    print(country_list)
    return render_template('index.html', countries=country_list,
                           calculated=calculated,
                           selected_country=selected_country, selected_date=selected_date,
                           calculation_rows=calculation_rows)

if __name__ == '__main__':
    app.run(debug=True)