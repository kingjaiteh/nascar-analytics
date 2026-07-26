
import pyreadr
import os

# Project root is this script's directory, so the script works from any checkout.
project_root = os.path.dirname(os.path.abspath(__file__))

# Define a function to handle the conversion
def convert_rda_to_csv(series_name):
    """Converts a specific series .rda file to .csv."""
    rda_file_path = os.path.join(project_root, 'nascaR.data', 'data', f'{series_name}.rda')
    csv_file_path = os.path.join(project_root, f'{series_name}_data.csv')
    
    try:
        # Read the .rda file
        result = pyreadr.read_r(rda_file_path)

        # Get the data frame from the dictionary
        # The object name in the .rda file is the same as the series name
        series_df = result[series_name]

        # Save the DataFrame to a CSV file
        series_df.to_csv(csv_file_path, index=False)

        print(f"Successfully converted {rda_file_path} to {csv_file_path}")

    except Exception as e:
        print(f"An error occurred while converting {series_name}: {e}")

# Convert both series
convert_rda_to_csv('truck_series')
convert_rda_to_csv('xfinity_series')
