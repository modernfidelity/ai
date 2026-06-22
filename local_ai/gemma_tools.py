import json
import ollama

# 1. Define the Python function Gemma 4 will call
def calculate_shipping(weight: float, destination: str) -> dict:
    """
    Calculates the exact shipping cost for a package.
    
    Args:
        weight: The weight of the package in kilograms (kg).
        destination: The city name where the package is going.
    """
    # Simple mock logic
    base_rate = 10.0 if destination.lower() == "london" else 15.0
    total_cost = base_rate + (weight * 2.5)
    return {"cost_usd": round(total_cost, 2), "status": "available"}

# Map the string name to the actual Python function object
available_tools = {
    "calculate_shipping": calculate_shipping
}

def main():
    # Define your question
    messages = [{
        "role": "user", 
        "content": "How much to ship a 4.5kg package to London?"
    }]
    
    print(f"Prompt: {messages[0]['content']}")

    # 2. Tell Ollama to use gemma4:latest and pass the function signature
    response = ollama.chat(
        model="gemma4:latest", 
        messages=messages,
        tools=[calculate_shipping]  # Ollama auto-inspects the function schema here
    )

    # 3. Check if Gemma decided to call your function
    if response.get("message", {}).get("tool_calls"):
        for tool in response["message"]["tool_calls"]:
            func_name = tool["function"]["name"]
            func_args = tool["function"]["arguments"]
            
            print(f"\n[Gemma 4 selected tool]: {func_name}")
            print(f"[Arguments provided]: {func_args}")
            
            # 4. Safely execute your local Python code
            if func_name in available_tools:
                tool_output = available_tools[func_name](**func_args)
                print(f"[Python Output]: {tool_output}")
                
                # 5. Append the conversation history so Gemma knows the results
                messages.append(response["message"])
                messages.append({
                    "role": "tool",
                    "content": json.dumps(tool_output)
                })
                
                # 6. Let Gemma 4 formulate the final answer for the user
                final_response = ollama.chat(model="gemma4:latest", messages=messages)
                print(f"\nFinal Answer: {final_response['message']['content']}")
    else:
        print(f"\nFinal Answer (No tool needed): {response['message']['content']}")

if __name__ == "__main__":
    main()
