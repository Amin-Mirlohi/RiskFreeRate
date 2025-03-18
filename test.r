# Load required packages
#library(YieldCurve)
library(minpack.lm)
library(lubridate)
library(dplyr)
# Load Amin's bond data
bond_data <- read.csv("C:\\Users\\phanouna\\Downloads\\cbonds_combined_type3_20250304.csv", stringsAsFactors = FALSE)
bond_data$Today <- today()
bond_data <- bond_data %>%
  mutate(
    Maturity = as.Date(Maturity), # Ensure Maturity is a Date
    Yearfrac = as.numeric(difftime(Maturity, Today, units = "days")) / 365
  )
bond_data$Indicative_yield <- bond_data$Indicative.yield...
bond_data <- bond_data %>% filter(Yearfrac>0.25) %>% filter(!is.na(Indicative_yield)) %>% filter(Indicative_yield <= 1)
# Define the NSS function
nss_function <- function(params, t, y) {
  beta0 <- params[1]
  beta1 <- params[2]
  beta2 <- params[3]
  beta3 <- params[4]
  tau1  <- params[5]
  tau2  <- params[6]
  # Nelson-Siegel-Svensson formula
  fitted_yield <- beta0 +
    beta1 * ((1 - exp(-t/tau1)) / (t/tau1)) +
    beta2 * (((1 - exp(-t/tau1)) / (t/tau1)) - exp(-t/tau1)) +
    beta3 * (((1 - exp(-t/tau2)) / (t/tau2)) - exp(-t/tau2))
  return(y - fitted_yield) # Residuals for optimization
}
# Initial NSS parameter guesses
init_params <- c(beta0 = 0.03, beta1 = -0.02, beta2 = 0.02, beta3 = 0.01, tau1 = 2.0, tau2 = 5.0)
# Get unique country codes
unique_countries <- unique(bond_data$Country)
# Store results for each country
nss_results <- list()
# Fit NSS curve for each country
for (country in unique_countries) {
  # Filter data for this country
  country_data <- bond_data %>% filter(Country == country)
  # Skip if there are too few bonds
  if (nrow(country_data) < 4) next
  # Fit NSS curve
  nss_fit <- tryCatch({
    nls.lm(par = init_params, fn = nss_function,
           t = country_data$Yearfrac, y = country_data$Indicative_yield)
  }, error = function(e) return(NULL))
  # Store results
  if (!is.null(nss_fit)) {
    nss_params <- coef(nss_fit)
    # Generate fitted yield curve
    fitted_yields <- nss_params[1] +
      nss_params[2] * ((1 - exp(-country_data$Yearfrac / nss_params[5])) / (country_data$Yearfrac / nss_params[5])) +
      nss_params[3] * (((1 - exp(-country_data$Yearfrac / nss_params[5])) / (country_data$Yearfrac / nss_params[5])) - exp(-country_data$Yearfrac / nss_params[5])) +
      nss_params[4] * (((1 - exp(-country_data$Yearfrac / nss_params[6])) / (country_data$Yearfrac / nss_params[6])) - exp(-country_data$Yearfrac / nss_params[6]))
    # Store NSS parameters and fitted values
    nss_results[[as.character(country)]] <- list(
      params = nss_params,
      fitted_yields = data.frame(Yearfrac = country_data$Yearfrac, Actual = country_data$Indicative_yield, Fitted = fitted_yields)
    )
  }
}
# Print results for each country
for (country in names(nss_results)) {
  cat("\nNSS Parameters for Country:", country, "\n")
  print(nss_results[[country]]$params)
}
library(ggplot2)
# Specify the country you want to plot
selected_country <- "119"
# Check if the selected country exists in the results
if (selected_country %in% names(nss_results)) {
  # Extract data for the specified country
  country_data <- nss_results[[selected_country]]$fitted_yields
  # Create the plot with percentage labels
  nss_plot <- ggplot(country_data, aes(x = Yearfrac)) +
    geom_point(aes(y = Actual), color = "red") +
    geom_line(aes(y = Fitted), color = "blue", linewidth = 1) +
    labs(title = paste("Nelson-Siegel-Svensson Yield Curve - Country", selected_country),
         x = "Years to Maturity", y = "Yield (%)") +
    # Fix y-axis scale and labels
    scale_y_continuous(labels = scales::percent_format(accuracy = 0.1),  # Ensure function is called properly
                       breaks = seq(0, max(country_data$Actual, na.rm = TRUE) * 1.2, by = 0.005)) +  # Granular y-grid (0.5% steps)
    # Improve x-axis granularity
    scale_x_continuous(breaks = seq(0, max(country_data$Yearfrac, na.rm = TRUE), by = 2)) +  # X-axis breaks every 2 years
    # Apply a clean theme
    theme_minimal()
  # Print the plot
  print(nss_plot)
} else {
  cat("No NSS results available for Country", selected_country, "\n")
}