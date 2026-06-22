# runner.py
import json
import inspect
import ollama
import my_tools  # Import your custom python tool file

def build_tool_registry(module):
    """Dynamically registers all user-defined functions in the tool file."""
    registry = {}
    functions_list = []
    
    # Iterate over everything inside the imported module
    for name, obj in inspect.getmembers(module):
        # Only select functions defined directly in that file (skip built-ins/imports)
        if inspect.isfunction(obj) and obj.__module__ == module.__name__:
            registry[name] = obj
            functions_list.append(obj)
            
    return registry, functions_list

def start_instance():
    # 1. Inspect and load tools dynamically from my_tools.py
    tools_registry, tools_list = build_tool_registry(my_tools)
    
    print("=" * 50)
    print(f"Local Gemma 4 Instance Initialized.")
    print(f"Loaded tools: {list(tools_registry.keys())}")
    print("=" * 50)
    
    # Setup conversation history
    messages = []
    
    while True:
        # Accept continuous user input
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ['exit', 'quit']:
            print("Shutting down model instance.")
            break
        if not user_input:
            continue
            
        messages.append({"role": "user", "content": user_input})
        
        # 2. Query Gemma 4 with our dynamic tools list
        response = ollama.chat(
            model="gemma4:latest",
            messages=messages,
            tools=tools_list
        )
        
        # 3. Handle Tool Execution Cycle
        if response.get("message", {}).get("tool_calls"):
            for tool_call in response["message"]["tool_calls"]:
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]
                
                print(f"\n[Gemma 4 requested tool]: {func_name}")
                print(f"[Arguments structured]: {func_args}")
                
                if func_name in tools_registry:
                    # Execute the real Python function safely from our registry
                    result = tools_registry[func_name](**func_args)
                    
                    # Feed execution history back to the model state
                    messages.append(response["message"])
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result)
                    })
                    
                    # Request final answered formulation from Gemma 4
                    final_response = ollama.chat(model="gemma4:latest", messages=messages)
                    print(f"\nGemma 4: {final_response['message']['content']}")
                    # Save final response to system memory for follow-up questions
                    messages.append(final_response["message"])
                else:
                    print(f"Error: Model requested tool '{func_name}', but it isn't in your tool file.")
        else:
            # Standard conversational response if no tool was required
            print(f"\Gemma 4: {response['message']['content']}")
            messages.append(response["message"])

if __name__ == "__main__":
    start_instance()
