import json
from rich import print as rprint
from json_repair import repair_json

def json_loads_robust(json_str):
    """
    robustly parse JSON from LLM responses.
    handles markdown code blocks and attempts repair if needed.
    """
    try:
        return json.loads(json_str)
    except Exception:
        pass

    data = json_str.split('```')[-2]
    if data.startswith('json'):
        data = data[len('json'):]

    try:
        return json.loads(data)
    except Exception:
        try:
            rprint(f"[yellow]error parsing JSON ... attempting repair[/yellow]")
            return json.loads(repair_json(data))
        except Exception as e:
            rprint(f"[red]error parsing JSON ... repair failed[/red]")
            print(data)
            raise e
