
import pyreadr
import os

# Project root is this script's directory, so the script works from any checkout.
project_root = os.path.dirname(os.path.abspath(__file__))
rda_file_path = os.path.join(project_root, 'nascaR.data', 'data', 'cup_series.rda')
csv_file_path = os.path.join(project_root, 'cup_series_data.csv')

try:
    # Read the .rda file
    result = pyreadr.read_r(rda_file_path)

    # Get the data frame from the dictionary
    cup_series_df = result['cup_series']

    # Save the DataFrame to a CSV file
    cup_series_df.to_csv(csv_file_path, index=False)

    print(f"Successfully converted {rda_file_path} to {csv_file_path}")

except Exception as e:
    print(f"An error occurred: {e}")
