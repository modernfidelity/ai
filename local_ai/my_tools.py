# my_tools.py

def fetch_local_weather(city: str) -> dict:
    """
    Retrieves the current weather report and temperature for a given city.
    
    Args:
        city: The name of the city to check weather for.
    """
    # Replace this mock logic with your actual API or database calls
    print(f"-> [Executing Python Code] Fetching weather data for: {city}")
    return {"temperature_celsius": 21.5, "condition": "Partly Cloudy", "humidity_percent": 62}

def search_text_file(filename: str, query: str) -> dict:
    """
    Searches a local text file for lines containing a specific keyword.
    
    Args:
        filename: The path or name of the text file.
        query: The keyword or phrase to search for.
    """
    print(f"-> [Executing Python Code] Searching {filename} for keyword: '{query}'")
    # Simple mockup of a local system file reader
    return {"matches_found": 3, "status": "Success", "preview": f"Found '{query}' on lines 4, 12, and 45."}
