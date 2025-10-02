# In src/controllers/utils.py

def deep_convert_to_dict(data):
    """
    Recursively converts Gemini's special MapComposite and ListComposite objects
    into standard Python dictionaries and lists.
    This version is more robust as it checks the object's class name and recurses into dicts/lists.
    """
    if hasattr(data, '__class__') and 'MapComposite' in data.__class__.__name__:
        return {key: deep_convert_to_dict(value) for key, value in data.items()}

    if hasattr(data, '__class__') and 'ListComposite' in data.__class__.__name__:
        return [deep_convert_to_dict(item) for item in data]

    if isinstance(data, dict):
        return {key: deep_convert_to_dict(value) for key, value in data.items()}

    if isinstance(data, list):
        return [deep_convert_to_dict(item) for item in data]

    return data